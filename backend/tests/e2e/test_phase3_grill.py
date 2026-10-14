"""E2E: Phase 3 Slice A — text grill start / answer / end."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


RESUME = """\
Jane Doe
Backend Engineer

EXPERIENCE

Acme Corp - Senior Engineer (2021-2024)
- Built billing API handling 2M req/day
- Reduced p99 latency 40% via caching
- Owned on-call for payments

SKILLS

Python, FastAPI, Postgres
"""


def _seed_ready(client: TestClient, duration: int = 15) -> str:
    # DEV_USER_ID is self-provisioned by the `client` fixture; session
    # ownership comes from the Bearer JWT, not body.user_id.
    from tests.e2e.conftest import DEV_USER_ID, ensure_user_exists

    ensure_user_exists(client, DEV_USER_ID, "dev@interviewbuddy.local", "Dev")
    session = client.post(
        "/sessions",
        json={
            "user_id": str(DEV_USER_ID),
            "settings": {
                "duration_minutes": duration,
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
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]
    deadline = time.time() + 60
    while time.time() < deadline:
        body = client.get(f"/sessions/{session_id}").json()
        if body["status"] in ("ready", "failed"):
            assert body["status"] == "ready", body
            return session_id
        time.sleep(0.15)
    raise AssertionError("session never ready")


def test_start_asks_first_question_and_answer_rotates(client: TestClient) -> None:
    session_id = _seed_ready(client)

    r = client.post(f"/sessions/{session_id}/start")
    assert r.status_code == 200, r.text
    live = r.json()
    assert live["status"] == "live"
    assert live["started_at"] is not None
    assert live["ends_at"] is not None

    turns = client.get(f"/sessions/{session_id}/turns").json()
    assert len(turns) >= 1
    assert turns[0]["role"] == "agent"
    assert turns[0]["raw_text"]

    topics = client.get(f"/sessions/{session_id}/topics").json()
    active = [t for t in topics if t["status"] == "active"]
    assert len(active) == 1
    assert active[0]["kind"] == "warmup"

    r = client.post(
        f"/sessions/{session_id}/answer",
        json={"text": "I don't know"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session"]["status"] == "live"
    assert body["agent_turn"] is not None
    assert body["agent_turn"]["role"] == "agent"

    topics = client.get(f"/sessions/{session_id}/topics").json()
    warmup = next(t for t in topics if t["kind"] == "warmup")
    assert warmup["status"] == "skipped"

    turns = client.get(f"/sessions/{session_id}/turns").json()
    assert any(t["role"] == "user" and "don't know" in t["raw_text"].lower() for t in turns)

    r = client.post(f"/sessions/{session_id}/end")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"

    topics = client.get(f"/sessions/{session_id}/topics").json()
    assert all(t["status"] in ("scored", "skipped") for t in topics)
    assert client.post(
        f"/sessions/{session_id}/answer",
        json={"text": "too late"},
    ).status_code == 409


def test_answer_rejected_when_not_live(client: TestClient) -> None:
    session_id = _seed_ready(client)
    r = client.post(
        f"/sessions/{session_id}/answer",
        json={"text": "hello"},
    )
    assert r.status_code == 409
