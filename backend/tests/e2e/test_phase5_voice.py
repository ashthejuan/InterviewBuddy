"""E2E: Phase 5 voice path — token endpoint + agent controller against real Postgres.

The controller is what the LiveKit worker calls on every final STT transcript, so driving it
directly exercises correction → grill → persistence without a media server.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import TypeVar

import pytest
from fastapi.testclient import TestClient
from livekit import api
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent.controller import CLOSING_LINE, VoiceGrillController
from app.config import get_settings
from tests.e2e.test_phase3_grill import _seed_ready

T = TypeVar("T")
LK_KEY = "devkey"
LK_SECRET = "e2e-secret-that-is-long-enough-for-hs256"


@pytest.fixture
def voice_configured(monkeypatch: pytest.MonkeyPatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "livekit_url", "ws://localhost:7880")
    monkeypatch.setattr(settings, "livekit_api_key", LK_KEY)
    monkeypatch.setattr(settings, "livekit_api_secret", LK_SECRET)
    return settings


@pytest.fixture
def voice_unconfigured(monkeypatch: pytest.MonkeyPatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "livekit_url", "")
    return settings


def _with_controller(
    session_id: str, fn: Callable[[VoiceGrillController], Awaitable[T]]
) -> T:
    """Own engine per event loop — asyncpg pools can't cross the TestClient loop."""

    async def run() -> T:
        engine = create_async_engine(get_settings().database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            return await fn(VoiceGrillController(uuid.UUID(session_id), factory))
        finally:
            await engine.dispose()

    return asyncio.run(run())


def test_voice_status_reflects_config(client: TestClient, voice_configured) -> None:
    assert client.get("/voice/status").json() == {"enabled": True}


def test_voice_status_disabled(client: TestClient, voice_unconfigured) -> None:
    assert client.get("/voice/status").json() == {"enabled": False}


def test_token_503_when_voice_unconfigured(client: TestClient, voice_unconfigured) -> None:
    session_id = _seed_ready(client)
    client.post(f"/sessions/{session_id}/start")
    assert client.post(f"/sessions/{session_id}/voice/token").status_code == 503


def test_token_requires_live_session(client: TestClient, voice_configured) -> None:
    assert client.post(f"/sessions/{uuid.uuid4()}/voice/token").status_code == 404

    session_id = _seed_ready(client)
    r = client.post(f"/sessions/{session_id}/voice/token")
    assert r.status_code == 409
    assert "start" in r.json()["detail"]

    assert client.post(f"/sessions/{session_id}/start").status_code == 200
    r = client.post(f"/sessions/{session_id}/voice/token")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["server_url"] == "ws://localhost:7880"
    claims = api.TokenVerifier(LK_KEY, LK_SECRET).verify(body["token"])
    assert claims.video.room == body["room_name"]
    assert session_id in body["room_name"]
    assert session_id in claims.room_config.agents[0].metadata

    client.post(f"/sessions/{session_id}/end")
    assert client.post(f"/sessions/{session_id}/voice/token").status_code == 409


def test_voice_turns_are_corrected_graded_and_persisted(client: TestClient) -> None:
    session_id = _seed_ready(client)
    assert client.post(f"/sessions/{session_id}/start").status_code == 200
    lexicon = client.get(f"/sessions/{session_id}").json()["lexicon"]
    assert "FastAPI" in lexicon["tools"] and "Postgres" in lexicon["tools"]

    async def scenario(ctl: VoiceGrillController):
        opening = await ctl.opening()
        again = await ctl.opening()  # reconnect → same question, no duplicate turn
        answer = await ctl.handle_final_transcript(
            "I built the billing service on fast api and postgress"
        )
        silence = await ctl.handle_final_transcript("   ")
        still_live = await ctl.poll()
        return opening, again, answer, silence, still_live

    opening, again, answer, silence, still_live = _with_controller(session_id, scenario)

    turns = client.get(f"/sessions/{session_id}/turns").json()
    assert opening.text == turns[0]["raw_text"] and not opening.done
    assert again.text == opening.text
    assert answer.text and not answer.done
    assert silence.text is None and not silence.done
    assert still_live is None

    user = next(t for t in turns if t["role"] == "user")
    assert user["raw_text"] == "I built the billing service on fast api and postgress"
    assert user["normalized_text"] == "I built the billing service on FastAPI and Postgres"
    assert [c["to"] for c in user["corrections"]] == ["FastAPI", "Postgres"]
    assert {c["method"] for c in user["corrections"]} == {"alias", "fuzzy"}
    assert turns[-1]["role"] == "agent" and turns[-1]["raw_text"] == answer.text
    assert len([t for t in turns if t["role"] == "agent"]) == 2


def test_timer_expiry_wraps_with_closing_line(client: TestClient) -> None:
    session_id = _seed_ready(client)
    client.post(f"/sessions/{session_id}/start")
    later = datetime.now(timezone.utc) + timedelta(hours=2)

    reply = _with_controller(session_id, lambda ctl: ctl.poll(now=later))
    assert reply is not None and reply.done and reply.text == CLOSING_LINE

    body = client.get(f"/sessions/{session_id}").json()
    assert body["status"] == "completed"
    assert body["settings"]["_grill"]["wrap_reason"] == "timer"
    topics = client.get(f"/sessions/{session_id}/topics").json()
    assert all(t["status"] in ("scored", "skipped") for t in topics)


def test_disconnect_wraps_and_later_turns_are_ignored(client: TestClient) -> None:
    session_id = _seed_ready(client)
    client.post(f"/sessions/{session_id}/start")

    async def scenario(ctl: VoiceGrillController):
        await ctl.on_disconnect()
        await ctl.on_disconnect()  # idempotent
        return await ctl.handle_final_transcript("hello?"), await ctl.poll()

    late, polled = _with_controller(session_id, scenario)
    assert late.done and late.text is None
    assert polled is not None and polled.done

    body = client.get(f"/sessions/{session_id}").json()
    assert body["status"] == "completed"
    assert body["settings"]["_grill"]["wrap_reason"] == "voice_disconnected"
    turns = client.get(f"/sessions/{session_id}/turns").json()
    assert not any(t["role"] == "user" for t in turns)


def test_external_end_stops_voice_agent(client: TestClient) -> None:
    session_id = _seed_ready(client)
    client.post(f"/sessions/{session_id}/start")
    client.post(f"/sessions/{session_id}/end")

    reply = _with_controller(session_id, lambda ctl: ctl.poll())
    assert reply is not None and reply.done and reply.text is None
    assert _with_controller(session_id, lambda ctl: ctl.opening()).done


def test_text_answers_also_store_corrections(client: TestClient) -> None:
    session_id = _seed_ready(client)
    client.post(f"/sessions/{session_id}/start")
    r = client.post(f"/sessions/{session_id}/answer", json={"text": "mostly python and fast api"})
    assert r.status_code == 200, r.text
    user = r.json()["user_turn"]
    assert user["raw_text"] == "mostly python and fast api"
    assert user["normalized_text"] == "mostly Python and FastAPI"
