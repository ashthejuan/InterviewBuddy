"""Report disk export → repo reports/report_N.{md,json}."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.report_export import next_report_paths, write_report_files


def test_next_report_paths_increments(tmp_path: Path) -> None:
    first = next_report_paths(tmp_path)
    assert first.markdown.name == "report_1.md"
    assert first.json_path.name == "report_1.json"
    assert first.pdf_path.name == "report_1.pdf"
    first.markdown.write_text("# hi\n")
    first.json_path.write_text("{}")
    first.pdf_path.write_bytes(b"%PDF")
    second = next_report_paths(tmp_path)
    assert second.markdown.name == "report_2.md"
    assert second.json_path.name == "report_2.json"
    assert second.pdf_path.name == "report_2.pdf"


def test_write_report_files_roundtrip(tmp_path: Path) -> None:
    report = {
        "schema_version": "v1",
        "session_meta": {"session_id": "abc"},
        "prose": {"summary": "Solid session.", "pros": [], "cons": [], "next_steps": []},
    }
    md = "# Interview debrief\n\nSolid session.\n"
    paths = write_report_files(report_json=report, report_markdown=md, directory=tmp_path)
    assert paths.markdown == tmp_path / "report_1.md"
    assert paths.json_path == tmp_path / "report_1.json"
    assert paths.pdf_path == tmp_path / "report_1.pdf"
    assert paths.markdown.read_text(encoding="utf-8") == md
    assert paths.pdf_path.read_bytes().startswith(b"%PDF-")
    loaded = json.loads(paths.json_path.read_text(encoding="utf-8"))
    assert loaded["report"]["session_meta"]["session_id"] == "abc"
    assert loaded["session_id"] == "abc"
    assert loaded["pdf_file"] == "report_1.pdf"
    assert "exported_at" in loaded
