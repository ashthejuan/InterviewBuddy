"""E2E: Phase 0 health + Phase 1 user/session CRUD against real Postgres."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_user_session_flow(client: TestClient) -> None:
    user_id = uuid.uuid4()
    email = f"e2e-{user_id.hex[:12]}@test.local"

    create_user = client.post(
        "/users",
        json={"id": str(user_id), "email": email, "name": "E2E"},
    )
    assert create_user.status_code == 201, create_user.text
    body = create_user.json()
    assert body["id"] == str(user_id)
    assert body["email"] == email

    get_user = client.get(f"/users/{user_id}")
    assert get_user.status_code == 200
    assert get_user.json()["email"] == email

    dup = client.post("/users", json={"email": email, "name": "Dup"})
    assert dup.status_code == 409

    create_session = client.post(
        "/sessions",
        json={
            "user_id": str(user_id),
            "settings": {
                "duration_minutes": 15,
                "difficulty": "hard",
                "seniority": "senior",
            },
        },
    )
    assert create_session.status_code == 201, create_session.text
    session = create_session.json()
    assert session["status"] == "preparing"
    assert session["user_id"] == str(user_id)
    assert session["settings"] == {
        "duration_minutes": 15,
        "difficulty": "hard",
        "seniority": "senior",
    }
    assert session["resume_document_id"] is None
    assert session["jd_document_id"] is None

    get_session = client.get(f"/sessions/{session['id']}")
    assert get_session.status_code == 200
    assert get_session.json()["status"] == "preparing"
    assert get_session.json()["settings"]["difficulty"] == "hard"


def test_session_requires_existing_user(client: TestClient) -> None:
    missing = uuid.uuid4()
    r = client.post("/sessions", json={"user_id": str(missing)})
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]


def test_get_missing_returns_404(client: TestClient) -> None:
    missing = uuid.uuid4()
    assert client.get(f"/users/{missing}").status_code == 404
    assert client.get(f"/sessions/{missing}").status_code == 404
