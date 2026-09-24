"""Unit tests for extract + normalize (PRD §3.1.1)."""

from __future__ import annotations

import io
import zipfile

import pytest

from app.services.extract import ExtractError, extract_bytes
from app.services.normalize import normalize_text


def test_normalize_strips_controls_and_nukes_nulls() -> None:
    raw = "Hello\x00World\x07\nNext"
    assert normalize_text(raw) == "HelloWorld\nNext"


def test_normalize_nfc() -> None:
    # e + combining acute → é
    raw = "cafe\u0301"
    out = normalize_text(raw)
    assert out == "caf\u00e9"


def test_extract_txt() -> None:
    text = extract_bytes(b"Line one\nLine two", kind="txt")
    assert "Line one" in text


def test_extract_md() -> None:
    text = extract_bytes(b"# Title\n\nBody", kind="md")
    assert "Title" in text


def test_extract_pdf_text() -> None:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject

    # Minimal text PDF via pypdf page
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    data = buf.getvalue()
    # blank page may yield empty — treat empty as failed scanned-like
    with pytest.raises(ExtractError, match="no extractable text|empty"):
        extract_bytes(data, kind="pdf")


def test_extract_pdf_with_text_content() -> None:
    # Hand-rolled tiny PDF with a text string
    pdf = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 200 200]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 44>>stream
BT /F1 12 Tf 10 100 Td (Alice Engineer) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
0000000361 00000 n 
trailer<</Size 6/Root 1 0 R>>
startxref
429
%%EOF
"""
    text = extract_bytes(pdf, kind="pdf")
    assert "Alice" in text or "Engineer" in text


def test_extract_rejects_too_many_pdf_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import extract as extract_mod

    monkeypatch.setattr(extract_mod, "MAX_PDF_PAGES", 1)

    # Two blank pages
    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(200, 200)
    w.add_blank_page(200, 200)
    buf = io.BytesIO()
    w.write(buf)
    with pytest.raises(ExtractError, match="pages"):
        extract_bytes(buf.getvalue(), kind="pdf")


def test_extract_docx() -> None:
    from docx import Document as DocxDocument

    doc = DocxDocument()
    doc.add_paragraph("Senior backend engineer")
    buf = io.BytesIO()
    doc.save(buf)
    text = extract_bytes(buf.getvalue(), kind="docx")
    assert "Senior backend engineer" in text


def test_extract_docx_rejects_zip_bomb(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import extract as extract_mod

    monkeypatch.setattr(extract_mod, "MAX_DOCX_UNCOMPRESSED_BYTES", 100)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", "x" * 1000)
        zf.writestr("[Content_Types].xml", "<Types/>")
    with pytest.raises(ExtractError, match="uncompressed|too large"):
        extract_bytes(buf.getvalue(), kind="docx")


def test_extract_rejects_over_char_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import extract as extract_mod

    monkeypatch.setattr(extract_mod, "MAX_EXTRACT_CHARS", 10)
    with pytest.raises(ExtractError, match="too long|chars"):
        extract_bytes(b"abcdefghijklmnop", kind="txt")
