"""Unit tests for upload validation (PRD §3.1.1)."""

from __future__ import annotations

import pytest

from app.services.validate_upload import UploadValidationError, validate_upload


def test_rejects_oversize() -> None:
    data = b"%PDF-1.4 " + b"x" * (5 * 1024 * 1024)
    with pytest.raises(UploadValidationError, match="too large"):
        validate_upload(data, filename="resume.pdf", content_type="application/pdf")


def test_rejects_extension_mismatch() -> None:
    data = b"%PDF-1.4 fake"
    with pytest.raises(UploadValidationError, match="mismatch|not allowed"):
        validate_upload(data, filename="resume.txt", content_type="application/pdf")


def test_rejects_unknown_extension() -> None:
    with pytest.raises(UploadValidationError, match="not allowed"):
        validate_upload(b"MZ\x90", filename="virus.exe", content_type="application/octet-stream")


def test_accepts_pdf_magic() -> None:
    data = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    result = validate_upload(data, filename="cv.pdf", content_type="application/pdf")
    assert result.kind == "pdf"
    assert result.content_type == "application/pdf"
    assert result.byte_size == len(data)


def test_accepts_txt() -> None:
    data = b"Jane Doe\nSoftware Engineer\n"
    result = validate_upload(data, filename="resume.txt", content_type="text/plain")
    assert result.kind == "txt"


def test_accepts_md() -> None:
    data = b"# Jane Doe\n\n- Python\n"
    result = validate_upload(data, filename="resume.md", content_type="text/markdown")
    assert result.kind == "md"


def test_rejects_docx_without_zip_magic() -> None:
    with pytest.raises(UploadValidationError):
        validate_upload(
            b"not-a-zip",
            filename="resume.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )


def test_paste_rejects_over_char_cap() -> None:
    from app.services.validate_upload import validate_paste

    with pytest.raises(UploadValidationError, match="too long"):
        validate_paste("x" * 100_001)


def test_paste_accepts_within_cap() -> None:
    from app.services.validate_upload import validate_paste

    text = "Hello resume"
    assert validate_paste(text) == text
