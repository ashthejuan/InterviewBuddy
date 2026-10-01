"""Interview transcript export → interview_logs/*.json."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.export_transcript import next_export_path, write_transcript_json


def test_next_export_path_increments(tmp_path: Path) -> None:
    assert next_export_path(tmp_path).name == "interview_1.json"
    (tmp_path / "interview_1.json").write_text("{}")
    (tmp_path / "interview_1.txt").write_text("old")
    assert next_export_path(tmp_path).name == "interview_2.json"


def test_write_transcript_json_roundtrip(tmp_path: Path) -> None:
    payload = {
        "session_id": "abc",
        "status": "completed",
        "turns": [{"role": "agent", "text": "Hi"}, {"role": "user", "text": "Hello"}],
    }
    path = write_transcript_json(payload, directory=tmp_path)
    assert path == tmp_path / "interview_1.json"
    loaded = json.loads(path.read_text())
    assert loaded["session_id"] == "abc"
    assert len(loaded["turns"]) == 2
