"""LiveKit room/token helpers + STT keyterms for the voice path (Phase 5)."""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from livekit import api

from app.config import Settings

ROOM_PREFIX = "ib-session-"
CANDIDATE_PREFIX = "candidate-"
MAX_KEYTERMS = 60
# Sarvam realtime `prompt` is a free-text hint; keep it short to avoid biasing ordinary speech.
MAX_PROMPT_CHARS = 500


class VoiceNotConfigured(RuntimeError):
    pass


@dataclass(frozen=True)
class VoiceGrant:
    server_url: str
    room_name: str
    participant_identity: str
    token: str
    expires_at: datetime


def room_name_for(session_id: uuid.UUID) -> str:
    """Fresh room per join: token dispatch only fires when the room is created."""
    return f"{ROOM_PREFIX}{session_id}-{secrets.token_hex(4)}"


def mint_voice_grant(
    *, session_id: uuid.UUID, user_id: uuid.UUID, settings: Settings
) -> VoiceGrant:
    if not settings.voice_enabled:
        raise VoiceNotConfigured("voice is not configured (LIVEKIT_URL / API key / secret)")
    room = room_name_for(session_id)
    identity = f"{CANDIDATE_PREFIX}{user_id}"
    ttl = timedelta(seconds=settings.livekit_token_ttl_seconds)
    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name("Candidate")
        .with_ttl(ttl)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=False,
                can_publish_sources=["microphone"],
            )
        )
        .with_room_config(
            api.RoomConfiguration(
                agents=[
                    api.RoomAgentDispatch(
                        agent_name=settings.livekit_agent_name,
                        metadata=json.dumps({"session_id": str(session_id)}),
                    )
                ],
            )
        )
        .to_jwt()
    )
    return VoiceGrant(
        server_url=settings.livekit_url,
        room_name=room,
        participant_identity=identity,
        token=token,
        expires_at=datetime.now(timezone.utc) + ttl,
    )


def parse_job_metadata(raw: str | None) -> uuid.UUID:
    """Session id from agent dispatch metadata. Raises ValueError on anything unexpected."""
    try:
        data = json.loads(raw or "")
    except json.JSONDecodeError as exc:
        raise ValueError("job metadata is not JSON") from exc
    if not isinstance(data, dict) or "session_id" not in data:
        raise ValueError("job metadata missing session_id")
    return uuid.UUID(str(data["session_id"]))


def lexicon_keyterms(lexicon: dict[str, Any] | None, *, limit: int = MAX_KEYTERMS) -> list[str]:
    """Session lexicon skills/tools/companies (deduped, no metrics) for STT biasing."""
    seen: set[str] = set()
    terms: list[str] = []
    for key in ("tools", "skills", "companies"):
        vals = (lexicon or {}).get(key) or []
        if not isinstance(vals, list):
            continue
        for v in vals:
            term = str(v).strip()
            if term and term.lower() not in seen:
                seen.add(term.lower())
                terms.append(term)
    return terms[:limit]


def stt_prompt(keyterms: list[str]) -> str | None:
    if not keyterms:
        return None
    prefix = "Technical interview. Terms that may be spoken: "
    out = prefix
    for i, term in enumerate(keyterms):
        piece = term if i == 0 else f", {term}"
        if len(out) + len(piece) > MAX_PROMPT_CHARS:
            break
        out += piece
    return out + "."
