#!/usr/bin/env python3
"""Generate a report for an existing completed session and save under `reports/`.

Usage (from backend/, Postgres required):
  uv run python scripts/run_session_report.py <session_uuid>
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.report_job import run_report_job


async def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: uv run python scripts/run_session_report.py <session_uuid>", file=sys.stderr)
        return 2
    session_id = uuid.UUID(argv[1])
    await run_report_job(session_id)
    print(f"Report job finished for {session_id} (see reports/ for disk copy when ready).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
