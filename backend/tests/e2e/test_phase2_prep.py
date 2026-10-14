"""E2E: prep finalize — embed, claims, lexicon, topics, start gate."""

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

JD = """\
# Backend Engineer

## Requirements
- 5+ years Python
- Experience with Postgres
- System design at scale
"""


def _seed_session(client: TestClient, duration: int = 30) -> str:
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
    return session["id"]


def _wait_doc(client: TestClient, doc_id: str, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/documents/{doc_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        if body["parse_status"] in ("ready", "failed"):
            return body
        time.sleep(0.15)
    raise AssertionError(f"document {doc_id} did not finish parsing")


def _wait_session(client: TestClient, session_id: str, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/sessions/{session_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        if body["status"] in ("ready", "failed", "live"):
            return body
        time.sleep(0.15)
    raise AssertionError(f"session {session_id} never left preparing")


def test_start_rejected_while_preparing(client: TestClient) -> None:
    session_id = _seed_session(client)
    r = client.post(f"/sessions/{session_id}/start")
    assert r.status_code == 409
    assert "not ready" in r.json()["detail"].lower()


def test_resume_prep_reaches_ready_with_embeddings_topics(client: TestClient) -> None:
    session_id = _seed_session(client)
    r = client.post(
        f"/sessions/{session_id}/documents/paste",
        json={"doc_type": "resume", "text": RESUME},
    )
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]
    done = _wait_doc(client, doc_id)
    assert done["parse_status"] == "ready", done

    sections = client.get(f"/documents/{doc_id}/sections").json()
    children = [
        c for s in sections for c in s["chunks"] if c["parent_chunk_id"] is not None
    ]
    assert children, "expected child chunks"
    assert any(c["has_embedding"] for c in children)

    session = _wait_session(client, session_id)
    assert session["status"] == "ready", session
    assert session["n_target"] is not None and session["n_target"] >= 1
    assert session["lexicon"]
    assert any(session["lexicon"].get(k) for k in ("skills", "tools", "metrics", "companies"))

    topics = client.get(f"/sessions/{session_id}/topics").json()
    assert len(topics) == session["n_target"]
    kinds = {t["kind"] for t in topics}
    assert "warmup" in kinds

    frontier = client.get(f"/sessions/{session_id}/frontier").json()
    assert len(frontier) == len(topics)
    assert all(n["status"] == "locked" for n in frontier)
    assert all(n["parent_id"] is None for n in frontier)

    start = client.post(f"/sessions/{session_id}/start")
    assert start.status_code == 200, start.text
    assert start.json()["status"] == "live"


def test_resume_plus_jd_ready(client: TestClient) -> None:
    session_id = _seed_session(client)
    r1 = client.post(
        f"/sessions/{session_id}/documents/paste",
        json={"doc_type": "resume", "text": RESUME},
    )
    r2 = client.post(
        f"/sessions/{session_id}/documents/paste",
        json={"doc_type": "jd", "text": JD},
    )
    assert r1.status_code == 201 and r2.status_code == 201
    assert _wait_doc(client, r1.json()["id"])["parse_status"] == "ready"
    assert _wait_doc(client, r2.json()["id"])["parse_status"] == "ready"

    session = _wait_session(client, session_id)
    assert session["status"] == "ready", session
    topics = client.get(f"/sessions/{session_id}/topics").json()
    kinds = {t["kind"] for t in topics}
    assert "jd_must" in kinds or "claim" in kinds
