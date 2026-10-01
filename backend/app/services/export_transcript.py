"""Write completed interview transcripts to repo `interview_logs/`."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_NUM_RE = re.compile(r"^interview_(\d+)\.(?:json|txt)$")


def repo_root() -> Path:
    # backend/app/services → repo root
    return Path(__file__).resolve().parents[3]


def interview_logs_dir() -> Path:
    d = repo_root() / "interview_logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def next_export_path(directory: Path | None = None) -> Path:
    directory = directory or interview_logs_dir()
    highest = 0
    for p in directory.iterdir():
        m = _NUM_RE.match(p.name)
        if m:
            highest = max(highest, int(m.group(1)))
    return directory / f"interview_{highest + 1}.json"


def write_transcript_json(
    payload: dict[str, Any],
    *,
    directory: Path | None = None,
) -> Path:
    path = next_export_path(directory)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def build_export_payload(
    *,
    session_id: str,
    status: str,
    settings: dict[str, Any],
    started_at: datetime | None,
    ends_at: datetime | None,
    turns: list[dict[str, Any]],
    topics: list[dict[str, Any]] | None = None,
    results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "status": status,
        "settings": settings,
        "started_at": started_at.isoformat() if started_at else None,
        "ends_at": ends_at.isoformat() if ends_at else None,
        "topics": topics or [],
        "turns": turns,
        "results": results,
    }
