"""API access-token verification (Auth.js → HS256 Bearer for FastAPI)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

API_ISSUER = "interviewbuddy"
API_AUDIENCE = "interviewbuddy-api"
ALGORITHM = "HS256"

_bearer = HTTPBearer(auto_error=False)
log = structlog.get_logger()


@dataclass(frozen=True)
class AuthedUser:
    id: uuid.UUID
    email: str | None


def mint_test_token(
    *,
    user_id: uuid.UUID,
    secret: str,
    email: str | None = None,
    ttl_seconds: int = 3600,
) -> str:
    """Mint an API access token (tests / local tooling)."""
    now = datetime.now(timezone.utc)
    payload: dict[str, object] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
        "iss": API_ISSUER,
        "aud": API_AUDIENCE,
    }
    if email:
        payload["email"] = email
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def verify_access_token(token: str, *, secret: str) -> AuthedUser:
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="auth is not configured (AUTH_SECRET)",
        )
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            audience=API_AUDIENCE,
            issuer=API_ISSUER,
        )
    except jwt.PyJWTError as exc:
        log.info("auth_token_invalid", reason=type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        log.info("auth_token_invalid", reason="missing_sub")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid access token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = uuid.UUID(sub)
    except ValueError as exc:
        log.info("auth_token_invalid", reason="bad_sub")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid access token subject",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    email = payload.get("email")
    return AuthedUser(
        id=user_id,
        email=email if isinstance(email, str) else None,
    )


def require_owner(user: AuthedUser, resource_user_id: uuid.UUID) -> None:
    if user.id != resource_user_id:
        log.info(
            "auth_forbidden",
            user_id=str(user.id),
            resource_user_id=str(resource_user_id),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ] = None,
) -> AuthedUser:
    settings = get_settings()
    if credentials is None or credentials.scheme.lower() != "bearer":
        log.info("auth_missing_bearer")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_access_token(credentials.credentials, secret=settings.auth_secret)
