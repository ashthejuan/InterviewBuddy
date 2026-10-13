"""Unit: LiveKit token minting, job metadata, STT keyterms (Phase 5)."""

from __future__ import annotations

import json
import uuid

import jwt
import pytest
from livekit import api

from app.config import Settings
from app.services.voice import (
    ROOM_PREFIX,
    VoiceNotConfigured,
    lexicon_keyterms,
    mint_voice_grant,
    parse_job_metadata,
    room_name_for,
    stt_prompt,
)

KEY = "devkey"
SECRET = "secret-that-is-long-enough-for-hs256-signing"


def _settings(**overrides) -> Settings:
    base = {
        "livekit_url": "ws://localhost:7880",
        "livekit_api_key": KEY,
        "livekit_api_secret": SECRET,
        "livekit_agent_name": "interviewbuddy-grill",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_grant_scopes_token_to_one_room_and_dispatches_agent() -> None:
    session_id, user_id = uuid.uuid4(), uuid.uuid4()
    grant = mint_voice_grant(session_id=session_id, user_id=user_id, settings=_settings())

    assert grant.server_url == "ws://localhost:7880"
    assert grant.room_name.startswith(f"{ROOM_PREFIX}{session_id}-")
    assert grant.participant_identity == f"candidate-{user_id}"

    claims = api.TokenVerifier(KEY, SECRET).verify(grant.token)
    assert claims.identity == grant.participant_identity
    assert claims.video.room_join is True
    assert claims.video.room == grant.room_name
    assert claims.video.can_publish_data is True
    assert claims.video.can_publish_sources == ["microphone"]
    assert claims.video.room_admin is not True

    agents = list(claims.room_config.agents)
    assert len(agents) == 1
    assert agents[0].agent_name == "interviewbuddy-grill"
    assert json.loads(agents[0].metadata) == {"session_id": str(session_id)}


def test_token_signed_with_other_secret_is_rejected() -> None:
    grant = mint_voice_grant(session_id=uuid.uuid4(), user_id=uuid.uuid4(), settings=_settings())
    with pytest.raises(jwt.InvalidSignatureError):
        api.TokenVerifier(KEY, "a-completely-different-secret-value-xx").verify(grant.token)


def test_unconfigured_voice_raises() -> None:
    with pytest.raises(VoiceNotConfigured):
        mint_voice_grant(
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            settings=_settings(livekit_api_secret=""),
        )


def test_room_name_is_fresh_per_join() -> None:
    sid = uuid.uuid4()
    assert room_name_for(sid) != room_name_for(sid)


def test_parse_job_metadata() -> None:
    sid = uuid.uuid4()
    assert parse_job_metadata(json.dumps({"session_id": str(sid)})) == sid
    for bad in (None, "", "not json", "[]", '{"x": 1}', '{"session_id": "nope"}'):
        with pytest.raises(ValueError):
            parse_job_metadata(bad)


def test_lexicon_keyterms_dedupes_and_skips_metrics() -> None:
    lexicon = {
        "skills": ["FastAPI", "Python"],
        "tools": ["FastAPI", "Postgres"],
        "companies": ["Acme Corp"],
        "metrics": ["40%"],
    }
    terms = lexicon_keyterms(lexicon)
    assert terms == ["FastAPI", "Postgres", "Python", "Acme Corp"]
    assert lexicon_keyterms(lexicon, limit=2) == ["FastAPI", "Postgres"]
    assert lexicon_keyterms(None) == []


def test_stt_prompt_is_bounded() -> None:
    assert stt_prompt([]) is None
    prompt = stt_prompt(["FastAPI", "Postgres"])
    assert prompt is not None and "FastAPI, Postgres" in prompt
    long_prompt = stt_prompt([f"Term{i:04d}" for i in range(500)])
    assert long_prompt is not None and len(long_prompt) <= 501
