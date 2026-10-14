"""Shared e2e client — one ASGI loop for the whole e2e package (asyncpg-safe)."""

from __future__ import annotations

import os
import uuid

# Force deterministic claims in e2e (no live OpenRouter dependency).
os.environ["CLAIMS_BACKEND"] = "heuristic"
os.environ["GRILL_BACKEND"] = "stub"
os.environ["SCORE_BACKEND"] = "heuristic"
os.environ["REPORT_BACKEND"] = "heuristic"
# Shared with frontend Auth.js — e2e mints Bearer tokens with this secret.
os.environ.setdefault("AUTH_SECRET", "e2e-auth-secret-at-least-32-chars-long")

import pytest
from fastapi.testclient import TestClient

from app.auth import mint_test_token
from app.config import get_settings
from app.main import app

get_settings.cache_clear()

DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture(scope="session")
def auth_secret() -> str:
    return get_settings().auth_secret


@pytest.fixture(scope="session")
def auth_header(auth_secret: str) -> dict[str, str]:
    token = mint_test_token(user_id=DEV_USER_ID, secret=auth_secret)
    return {"Authorization": f"Bearer {token}"}


def ensure_user_exists(
    client: TestClient, user_id: uuid.UUID, email: str, name: str = "E2E"
) -> None:
    """Idempotently self-provision `user_id` (POST /users requires id == JWT sub)."""
    r = client.post(
        "/users",
        json={"id": str(user_id), "email": email, "name": name},
    )
    assert r.status_code in (201, 409), r.text


@pytest.fixture(scope="session")
def client(auth_header: dict[str, str]):
    with TestClient(app) as c:
        c.headers.update(auth_header)
        ensure_user_exists(c, DEV_USER_ID, "dev@interviewbuddy.local", "Dev")
        yield c


@pytest.fixture(scope="session")
def bare_client():
    """Unauthenticated client (no default Bearer header) for 401 matrix tests."""
    with TestClient(app) as c:
        yield c
