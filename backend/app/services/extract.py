"""Format-specific text extraction with bounds (PRD §3.1.1)."""

from __future__ import annotations

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

MAX_PDF_PAGES = 30
MAX_DOCX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
MAX_EXTRACT_CHARS = 100_000
EXTRACT_TIMEOUT_SECONDS = 10


class ExtractError(ValueError):
    pass


def extract_bytes(data: bytes, *, kind: str) -> str:
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_extract_sync, data, kind)
            text = fut.result(timeout=EXTRACT_TIMEOUT_SECONDS)
    except FuturesTimeout as exc:
        raise ExtractError("document parse timed out") from exc

    if len(text) > MAX_EXTRACT_CHARS:
        raise ExtractError(f"extracted text too long (max {MAX_EXTRACT_CHARS} chars)")
    return text


def _extract_sync(data: bytes, kind: str) -> str:
    if kind == "txt":
        return _decode_text(data)
    if kind == "md":
        return _decode_text(data)
    if kind == "pdf":
        return _extract_pdf(data)
    if kind == "docx":
        return _extract_docx(data)
    raise ExtractError(f"unsupported kind: {kind}")


def _decode_text(data: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ExtractError("could not decode text")


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 — surface as parse failure
        raise ExtractError(f"invalid PDF: {exc}") from exc

    if len(reader.pages) > MAX_PDF_PAGES:
        raise ExtractError(f"PDF has too many pages (max {MAX_PDF_PAGES})")

    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    text = "\n".join(parts).strip()
    if not text:
        raise ExtractError("no extractable text (scanned or empty PDF)")
    return text


def _docx_uncompressed_size(data: bytes) -> int:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return sum(info.file_size for info in zf.infolist())


def _extract_docx(data: bytes) -> str:
    try:
        uncompressed = _docx_uncompressed_size(data)
    except zipfile.BadZipFile as exc:
        raise ExtractError("invalid DOCX (not a zip)") from exc

    if uncompressed > MAX_DOCX_UNCOMPRESSED_BYTES:
        raise ExtractError(
            f"DOCX uncompressed too large (max {MAX_DOCX_UNCOMPRESSED_BYTES} bytes)"
        )

    from docx import Document as DocxDocument

    try:
        doc = DocxDocument(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise ExtractError(f"invalid DOCX: {exc}") from exc

    paras = [p.text for p in doc.paragraphs if p.text]
    text = "\n".join(paras).strip()
    if not text:
        raise ExtractError("no extractable text (empty DOCX)")
    return text
