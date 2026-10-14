"""E2E: session/doc/user/voice routes require Bearer auth + ownership.

Matrix:
- missing Bearer -> 401 on every protected route (incl. POST /users, GET /users/{id})
- invalid Bearer -> 401
- valid Bearer for a different user -> 403 on every owned route
- public routes (/health, GET /voice/status) stay reachable without auth
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth import mint_test_token
from app.config import get_settings
from tests.e2e.conftest import DEV_USER_ID, ensure_user_exists
from tests.e2e.test_phase3_grill import _seed_ready


def _other_headers() -> dict[str, str]:
    other = uuid.uuid4()
    token = mint_test_token(user_id=other, secret=get_settings().auth_secret)
    return {"Authorization": f"Bearer {token}"}


def _bad_headers() -> dict[str, str]:
    return {"Authorization": "Bearer not-a-valid-token"}


def _unauth_requests(session_id: uuid.UUID, doc_id: uuid.UUID, user_id: uuid.UUID):
    """(method, path, kwargs) for every protected route — random but well-formed ids."""
    sid, did, uid = str(session_id), str(doc_id), str(user_id)
    return [
        ("POST", "/users", {"json": {"id": uid, "email": f"m-{uid[:8]}@t.local"}}),
        ("GET", f"/users/{uid}", {}),
        ("POST", "/sessions", {"json": {"settings": {}}}),
        ("GET", f"/sessions/{sid}", {}),
        ("POST", f"/sessions/{sid}/start", {}),
        ("GET", f"/sessions/{sid}/turns", {}),
        ("POST", f"/sessions/{sid}/answer", {"json": {"text": "hello"}}),
        ("POST", f"/sessions/{sid}/end", {}),
        ("GET", f"/sessions/{sid}/report", {}),
        ("POST", f"/sessions/{sid}/report/retry", {}),
        ("GET", f"/sessions/{sid}/report.pdf", {}),
        ("GET", f"/sessions/{sid}/results", {}),
        ("POST", f"/sessions/{sid}/export", {}),
        ("POST", f"/sessions/{sid}/voice/token", {}),
        ("GET", f"/sessions/{sid}/topics", {}),
        ("GET", f"/sessions/{sid}/frontier", {}),
        ("GET", f"/documents/{did}", {}),
        ("GET", f"/documents/{did}/sections", {}),
        (
            "POST",
            f"/sessions/{sid}/documents",
            {"data": {"doc_type": "resume"}, "files": {"file": ("r.txt", b"hi", "text/plain")}},
        ),
        (
            "POST",
            f"/sessions/{sid}/documents/paste",
            {"json": {"doc_type": "resume", "text": "hello world"}},
        ),
    ]


def test_protected_routes_require_auth(bare_client: TestClient) -> None:
    ids = (uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    for method, path, kwargs in _unauth_requests(*ids):
        r = bare_client.request(method, path, **kwargs)
        assert r.status_code == 401, f"{method} {path} -> {r.status_code}: {r.text}"


def test_protected_routes_reject_invalid_bearer(client: TestClient) -> None:
    ids = (uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    bad = _bad_headers()
    for method, path, kwargs in _unauth_requests(*ids):
        r = client.request(method, path, headers=bad, **kwargs)
        assert r.status_code == 401, f"{method} {path} -> {r.status_code}: {r.text}"


def test_voice_token_rejects_invalid_bearer(client: TestClient) -> None:
    session_id = _seed_ready(client)
    client.post(f"/sessions/{session_id}/start")
    r = client.post(
        f"/sessions/{session_id}/voice/token",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )
    assert r.status_code == 401


def test_session_get_forbidden_for_other_user(client: TestClient) -> None:
    session_id = _seed_ready(client)
    other = uuid.uuid4()
    token = mint_test_token(user_id=other, secret=get_settings().auth_secret)
    r = client.get(
        f"/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


def test_owned_routes_forbid_cross_user(client: TestClient) -> None:
    ensure_user_exists(client, DEV_USER_ID, "dev@interviewbuddy.local", "Dev")
    session_id = _seed_ready(client)
    session = client.get(f"/sessions/{session_id}").json()
    doc_id = session.get("resume_document_id")
    assert doc_id, f"seeded session has no resume doc: {session}"

    other_headers = _other_headers()
    sid, did = str(session_id), str(doc_id)
    owned = [
        ("GET", f"/sessions/{sid}", {}),
        ("POST", f"/sessions/{sid}/start", {}),
        ("GET", f"/sessions/{sid}/turns", {}),
        ("POST", f"/sessions/{sid}/answer", {"json": {"text": "hello"}}),
        ("POST", f"/sessions/{sid}/end", {}),
        ("GET", f"/sessions/{sid}/report", {}),
        ("POST", f"/sessions/{sid}/report/retry", {}),
        ("GET", f"/sessions/{sid}/report.pdf", {}),
        ("GET", f"/sessions/{sid}/results", {}),
        ("POST", f"/sessions/{sid}/export", {}),
        ("GET", f"/sessions/{sid}/topics", {}),
        ("GET", f"/sessions/{sid}/frontier", {}),
        ("GET", f"/documents/{did}", {}),
        ("GET", f"/documents/{did}/sections", {}),
        (
            "POST",
            f"/sessions/{sid}/documents",
            {"data": {"doc_type": "resume"}, "files": {"file": ("r.txt", b"hi", "text/plain")}},
        ),
        (
            "POST",
            f"/sessions/{sid}/documents/paste",
            {"json": {"doc_type": "resume", "text": "hello world"}},
        ),
        # User routes: DEV token cannot touch the other user, and vice versa.
        ("GET", f"/users/{DEV_USER_ID}", {}),
        ("POST", "/users", {"json": {"id": str(DEV_USER_ID), "email": "x@t.local"}}),
    ]
    for method, path, kwargs in owned:
        r = client.request(method, path, headers=other_headers, **kwargs)
        # Ownership is checked before status/voice gates, so every owned
        # route must be 403 for a non-owner (no existence/status leakage).
        assert r.status_code == 403, f"{method} {path} -> {r.status_code}: {r.text}"

    # Voice token also enforces ownership, but only after the server-side
    # voice-enabled gate: accept 503 when voice is not configured.
    r = client.post(f"/sessions/{sid}/voice/token", headers=other_headers)
    assert r.status_code in (403, 503), f"voice/token -> {r.status_code}: {r.text}"
    if r.status_code == 503:
        pytest.skip("voice not configured — ownership gate unreachable")


def test_user_routes_self_only(client: TestClient) -> None:
    other = uuid.uuid4()
    # Cross-user create + read are 403 (no oracle on existence).
    assert (
        client.post(
            "/users", json={"id": str(other), "email": f"sq-{other.hex[:8]}@test.local"}
        ).status_code
        == 403
    )
    assert client.get(f"/users/{other}").status_code == 403


def test_public_routes_without_auth(bare_client: TestClient) -> None:
    assert bare_client.get("/health").status_code == 200
    # Voice capability flag is intentionally public (boolean only, no user data).
    assert bare_client.get("/voice/status").status_code == 200
