"""Phase 6 — markdown → PDF bytes for download."""

from __future__ import annotations

from app.services.report_pdf import render_report_pdf


def test_render_report_pdf_returns_pdf_bytes() -> None:
    md = "# Interview debrief\n\n**solid** · 3.5 / 5\n\n- Latency work\n"
    pdf = render_report_pdf(md)
    assert pdf.startswith(b"%PDF-")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert b"/Type /Page" in pdf or b"/Type/Page" in pdf


def test_render_report_pdf_embeds_plain_text() -> None:
    md = "# Interview debrief\n\nPractice signal: solid\nNext steps here\n"
    pdf = render_report_pdf(md)
    # Content is stored as PDF text strings; latin-1 safe phrases should appear.
    assert b"Interview debrief" in pdf or b"Practice signal" in pdf
