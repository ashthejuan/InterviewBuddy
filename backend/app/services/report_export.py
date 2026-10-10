"""Write completed interview reports to repo `reports/`."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.report_pdf import render_report_pdf

_NUM_RE = re.compile(r"^report_(\d+)\.(?:md|json|pdf)$")


def repo_root() -> Path:
    # backend/app/services → repo root
    return Path(__file__).resolve().parents[3]


def reports_dir() -> Path:
    d = repo_root() / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass(frozen=True)
class ReportDiskPaths:
    markdown: Path
    json_path: Path
    pdf_path: Path


def next_report_paths(directory: Path | None = None) -> ReportDiskPaths:
    directory = directory or reports_dir()
    directory.mkdir(parents=True, exist_ok=True)
    highest = 0
    for p in directory.iterdir():
        m = _NUM_RE.match(p.name)
        if m:
            highest = max(highest, int(m.group(1)))
    n = highest + 1
    return ReportDiskPaths(
        markdown=directory / f"report_{n}.md",
        json_path=directory / f"report_{n}.json",
        pdf_path=directory / f"report_{n}.pdf",
    )


def write_report_files(
    *,
    report_json: dict[str, Any],
    report_markdown: str,
    directory: Path | None = None,
    session_id: str | None = None,
) -> ReportDiskPaths:
    """Persist markdown + JSON + PDF under `reports/` (auto-incrementing)."""
    paths = next_report_paths(directory)
    sid = session_id or str((report_json.get("session_meta") or {}).get("session_id") or "")
    md = report_markdown if report_markdown.endswith("\n") else report_markdown + "\n"
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "session_id": sid,
        "report": report_json,
        "markdown_file": paths.markdown.name,
        "pdf_file": paths.pdf_path.name,
    }
    paths.markdown.write_text(md, encoding="utf-8")
    paths.json_path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    paths.pdf_path.write_bytes(render_report_pdf(md))
    return paths
