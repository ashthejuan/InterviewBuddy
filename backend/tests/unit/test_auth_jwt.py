"""Unit: Auth.js-compatible API JWT verify + ownership helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.auth import AuthedUser, mint_test_token, require_owner, verify_access_token


def test_verify_access_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    token = mint_test_token(user_id=user_id, secret="unit-test-secret-at-least-32-chars")
    authed = verify_access_token(token, secret="unit-test-secret-at-least-32-chars")
    assert authed.id == user_id
    assert authed.email is None


def test_verify_rejects_bad_signature() -> None:
    user_id = uuid.uuid4()
    token = mint_test_token(user_id=user_id, secret="unit-test-secret-at-least-32-chars")
    with pytest.raises(HTTPException) as exc:
        verify_access_token(token, secret="other-secret-that-is-long-enough!!")
    assert exc.value.status_code == 401


def test_verify_rejects_expired() -> None:
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "iss": "interviewbuddy",
            "aud": "interviewbuddy-api",
        },
        "unit-test-secret-at-least-32-chars",
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc:
        verify_access_token(token, secret="unit-test-secret-at-least-32-chars")
    assert exc.value.status_code == 401


def test_require_owner_allows_match() -> None:
    uid = uuid.uuid4()
    require_owner(AuthedUser(id=uid, email=None), uid)


def test_require_owner_forbids_mismatch() -> None:
    with pytest.raises(HTTPException) as exc:
        require_owner(AuthedUser(id=uuid.uuid4(), email=None), uuid.uuid4())
    assert exc.value.status_code == 403
