"""E2E: session/doc/voice routes require Bearer auth + ownership."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.auth import mint_test_token
from app.config import get_settings
from tests.e2e.test_phase3_grill import _seed_ready


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
