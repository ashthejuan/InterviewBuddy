"""E2E: Phase 0 health + Phase 1 user/session CRUD against real Postgres."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.auth import mint_test_token
from app.config import get_settings
from tests.e2e.conftest import DEV_USER_ID, ensure_user_exists


def test_health(client: TestClient, bare_client: TestClient) -> None:
    for c in (client, bare_client):
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


def test_user_self_provisioning_flow(client: TestClient) -> None:
    # DEV_USER_ID is self-provisioned by the `client` fixture; re-seeding is idempotent.
    ensure_user_exists(client, DEV_USER_ID, "dev@interviewbuddy.local", "Dev")

    get_self = client.get(f"/users/{DEV_USER_ID}")
    assert get_self.status_code == 200
    assert get_self.json()["id"] == str(DEV_USER_ID)

    # Self-provisioning a fresh user with its own token succeeds.
    fresh_id = uuid.uuid4()
    fresh_email = f"e2e-{fresh_id.hex[:12]}@test.local"
    fresh_token = mint_test_token(user_id=fresh_id, secret=get_settings().auth_secret)
    fresh_headers = {"Authorization": f"Bearer {fresh_token}"}
    create_fresh = client.post(
        "/users",
        json={"id": str(fresh_id), "email": fresh_email, "name": "E2E"},
        headers=fresh_headers,
    )
    assert create_fresh.status_code in (201, 409), create_fresh.text

    get_fresh = client.get(f"/users/{fresh_id}", headers=fresh_headers)
    assert get_fresh.status_code == 200
    assert get_fresh.json()["email"] == fresh_email

    # Duplicate email (self id, taken email) is rejected.
    dup_id = uuid.uuid4()
    dup_token = mint_test_token(user_id=dup_id, secret=get_settings().auth_secret)
    dup = client.post(
        "/users",
        json={"id": str(dup_id), "email": fresh_email, "name": "Dup"},
        headers={"Authorization": f"Bearer {dup_token}"},
    )
    assert dup.status_code == 409

    # Session ownership comes from the Bearer JWT (DEV_USER_ID in conftest), not body.user_id.
    create_session = client.post(
        "/sessions",
        json={
            "user_id": str(fresh_id),  # ignored
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
    assert session["user_id"] == str(DEV_USER_ID)
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


def test_user_routes_reject_cross_user(client: TestClient) -> None:
    other = uuid.uuid4()
    # DEV token cannot create a different user id.
    r = client.post(
        "/users",
        json={"id": str(other), "email": f"sq-{other.hex[:8]}@test.local"},
    )
    assert r.status_code == 403
    # DEV token cannot read a different user (existence oracle closed -> 403, not 404).
    assert client.get(f"/users/{other}").status_code == 403


def test_session_requires_existing_user(client: TestClient) -> None:
    missing = uuid.uuid4()
    token = mint_test_token(user_id=missing, secret=get_settings().auth_secret)
    r = client.post(
        "/sessions",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]


def test_get_missing_returns_404(client: TestClient) -> None:
    missing = uuid.uuid4()
    assert client.get(f"/sessions/{missing}").status_code == 404
