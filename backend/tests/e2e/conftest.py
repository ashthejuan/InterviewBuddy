"""Shared e2e client — one ASGI loop for the whole e2e package (asyncpg-safe)."""

from __future__ import annotations

import os

# Force deterministic claims in e2e (no live OpenRouter dependency).
os.environ["CLAIMS_BACKEND"] = "heuristic"

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

get_settings.cache_clear()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
