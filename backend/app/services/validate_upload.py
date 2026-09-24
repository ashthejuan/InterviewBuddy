"""Upload allowlist + size/sniff validation (PRD §3.1.1)."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MAX_UPLOAD_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_PASTE_CHARS = 100_000

_EXT_KIND = {
    ".pdf": "pdf",
    ".txt": "txt",
    ".md": "md",
    ".markdown": "md",
    ".docx": "docx",
}

_KIND_CONTENT_TYPE = {
    "pdf": "application/pdf",
    "txt": "text/plain",
    "md": "text/markdown",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class UploadValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedUpload:
    kind: str
    content_type: str
    byte_size: int
    original_filename: str


def _extension(filename: str) -> str:
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1].lower()


def _sniff_kind(data: bytes) -> str | None:
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(b"PK\x03\x04") or data.startswith(b"PK\x05\x06"):
        return "docx"  # zip container; DOCX confirmed by extension allowlist
    # UTF-8 BOM or printable-ish text
    sample = data[:512].lstrip(b"\xef\xbb\xbf")
    if not sample:
        return "txt"
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if b"\x00" in sample:
        return None
    return "txt"  # md shares text sniff; extension disambiguates


def validate_upload(
    data: bytes,
    *,
    filename: str,
    content_type: str | None,
    max_bytes: int | None = None,
) -> ValidatedUpload:
    limit = max_bytes if max_bytes is not None else DEFAULT_MAX_UPLOAD_BYTES
    if len(data) > limit:
        raise UploadValidationError(f"file too large (max {limit} bytes)")

    ext = _extension(filename)
    if ext not in _EXT_KIND:
        raise UploadValidationError(f"file type not allowed ({ext or 'no extension'})")

    kind = _EXT_KIND[ext]
    sniffed = _sniff_kind(data)
    if kind == "pdf" and sniffed != "pdf":
        raise UploadValidationError("content mismatch: expected PDF magic bytes")
    if kind == "docx" and sniffed != "docx":
        raise UploadValidationError("content mismatch: expected DOCX/ZIP magic bytes")
    if kind in ("txt", "md") and sniffed not in ("txt", None):
        # binary sniffed as pdf/docx
        if sniffed in ("pdf", "docx"):
            raise UploadValidationError("content mismatch: binary content for text upload")
    if kind in ("txt", "md") and sniffed is None:
        raise UploadValidationError("content mismatch: not valid UTF-8 text")

    return ValidatedUpload(
        kind=kind,
        content_type=_KIND_CONTENT_TYPE[kind],
        byte_size=len(data),
        original_filename=filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1],
    )


def validate_paste(text: str, *, max_chars: int | None = None) -> str:
    limit = max_chars if max_chars is not None else DEFAULT_MAX_PASTE_CHARS
    if len(text) > limit:
        raise UploadValidationError(f"paste too long (max {limit} characters)")
    return text
