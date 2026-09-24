"""Shared e2e client — one ASGI loop for the whole e2e package (asyncpg-safe)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
