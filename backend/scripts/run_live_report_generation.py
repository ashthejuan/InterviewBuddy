#!/usr/bin/env python3
"""End-to-end report generation against local Postgres → writes under repo `reports/`.

Usage (from backend/, Postgres + MinIO up):
  uv run python scripts/run_live_report_generation.py
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("CLAIMS_BACKEND", "heuristic")
os.environ.setdefault("GRILL_BACKEND", "stub")
os.environ.setdefault("SCORE_BACKEND", "heuristic")
os.environ.setdefault("REPORT_BACKEND", "heuristic")

from app.config import get_settings
from fastapi.testclient import TestClient

from app.main import app
from app.services.report_export import reports_dir
from tests.e2e.test_phase3_grill import RESUME
from tests.e2e.test_phase4_scoring import DETAILED


def _wait_ready(client: TestClient, session_id: str) -> None:
    deadline = time.time() + 60
    while time.time() < deadline:
        body = client.get(f"/sessions/{session_id}").json()
        if body["status"] in ("ready", "failed"):
            if body["status"] != "ready":
                raise SystemExit(f"prep failed: {body}")
            return
        time.sleep(0.15)
    raise SystemExit("session never ready")


def _wait_report(client: TestClient, session_id: str) -> dict:
    deadline = time.time() + 45
    last = None
    while time.time() < deadline:
        r = client.get(f"/sessions/{session_id}/report")
        r.raise_for_status()
        last = r.json()
        if last["status"] in ("ready", "failed"):
            return last
        time.sleep(0.25)
    raise SystemExit(f"report never finished: {last}")


def main() -> int:
    get_settings.cache_clear()
    before = {p.name for p in reports_dir().glob("report_*")}

    with TestClient(app) as client:
        user_id = uuid.uuid4()
        client.post(
            "/users",
            json={
                "id": str(user_id),
                "email": f"report-run-{user_id.hex[:10]}@test.local",
                "name": "Report Run",
            },
        ).raise_for_status()
        session = client.post(
            "/sessions",
            json={
                "user_id": str(user_id),
                "settings": {
                    "duration_minutes": 30,
                    "difficulty": "medium",
                    "seniority": "mid",
                },
            },
        ).json()
        session_id = session["id"]
        r = client.post(
            f"/sessions/{session_id}/documents/paste",
            json={"doc_type": "resume", "text": RESUME},
        )
        r.raise_for_status()
        _wait_ready(client, session_id)
        client.post(f"/sessions/{session_id}/start").raise_for_status()
        client.post(f"/sessions/{session_id}/answer", json={"text": "I don't know"}).raise_for_status()
        client.post(f"/sessions/{session_id}/answer", json={"text": DETAILED}).raise_for_status()
        client.post(f"/sessions/{session_id}/end").raise_for_status()
        out = _wait_report(client, session_id)

    if out["status"] != "ready":
        print(out, file=sys.stderr)
        return 1

    after = sorted(p for p in reports_dir().glob("report_*") if p.name not in before)
    print(f"session_id={session_id}")
    print(f"hire_signal={out['report_json']['overall_signal']['hire_signal']}")
    print(f"summary={out['report_json']['prose']['summary']}")
    for p in after:
        print(f"wrote {p}")
    if not after:
        print("warning: no new files under reports/ (job may have failed disk write)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
