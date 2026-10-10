"""E2E: Phase 6 — structured report job + disk write under reports/."""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.services import report_export
from tests.e2e.test_phase3_grill import _seed_ready
from tests.e2e.test_phase4_scoring import DETAILED


def _wait_report(client: TestClient, session_id: str, *, timeout: float = 45.0) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = client.get(f"/sessions/{session_id}/report")
        assert r.status_code == 200, r.text
        last = r.json()
        if last["status"] in ("ready", "failed"):
            return last
        time.sleep(0.25)
    raise AssertionError(f"report never finished: {last}")


def test_completed_session_report_ready_and_saved_to_disk(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    def _write(**kwargs):
        kwargs["directory"] = tmp_path
        return report_export.write_report_files(**kwargs)

    monkeypatch.setattr("app.services.report_job.write_report_files", _write)

    session_id = _seed_ready(client, duration=30)
    assert client.post(f"/sessions/{session_id}/start").status_code == 200
    client.post(f"/sessions/{session_id}/answer", json={"text": "I don't know"})
    client.post(f"/sessions/{session_id}/answer", json={"text": DETAILED})
    assert client.post(f"/sessions/{session_id}/end").status_code == 200

    out = _wait_report(client, session_id)
    assert out["status"] == "ready", out
    assert out["report_json"]["schema_version"] == "v1"
    assert out["report_json"]["prose"]["summary"]
    assert out["report_markdown"].startswith("# Interview debrief")
    assert out["report_json"]["prose"]["next_steps"]

    md_files = sorted(tmp_path.glob("report_*.md"))
    json_files = sorted(tmp_path.glob("report_*.json"))
    assert len(md_files) >= 1, f"expected disk report under {tmp_path}"
    assert len(json_files) >= 1
    assert "Interview debrief" in md_files[-1].read_text(encoding="utf-8")
    sidecar = json.loads(json_files[-1].read_text(encoding="utf-8"))
    assert sidecar["session_id"] == session_id
    assert sidecar["report"]["schema_version"] == "v1"


def test_report_retry_endpoint_resets_to_pending(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    def _write(**kwargs):
        kwargs["directory"] = tmp_path
        return report_export.write_report_files(**kwargs)

    monkeypatch.setattr("app.services.report_job.write_report_files", _write)

    session_id = _seed_ready(client)
    client.post(f"/sessions/{session_id}/start")
    client.post(f"/sessions/{session_id}/end")
    ready = _wait_report(client, session_id)
    assert ready["status"] == "ready"

    r = client.post(f"/sessions/{session_id}/report/retry")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"

    again = _wait_report(client, session_id)
    assert again["status"] == "ready"
