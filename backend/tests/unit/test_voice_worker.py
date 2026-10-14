"""Unit: LiveKit worker adapters — STT/TTS selection, speak(), user-turn hook (Phase 5)."""

from __future__ import annotations

import asyncio

import pytest
from livekit.agents import ChatContext, ChatMessage, StopResponse
from livekit.plugins import sarvam

from agent.controller import CLOSING_LINE, VoiceReply
from agent.worker import (
    BULBUL_V4_DEFAULT_SPEAKER,
    TURN_HANDLING,
    GrillVoiceAgent,
    build_stt,
    build_tts,
    speak,
)
from app.config import Settings


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, sarvam_api_key="test-key", **overrides)


class FakeSession:
    def __init__(self) -> None:
        self.said: list[tuple[str, bool]] = []
        self.shutdowns: list[bool] = []

    def say(self, text: str, *, allow_interruptions: bool = True) -> None:
        self.said.append((text, allow_interruptions))

    def shutdown(self, *, drain: bool = True) -> None:
        self.shutdowns.append(drain)


class FakeController:
    def __init__(self, reply: VoiceReply, streamed: list[str] | None = None) -> None:
        self.reply = reply
        self.streamed = streamed
        self.heard: list[str] = []

    def _maybe_stream(self, start_speech) -> None:
        if self.streamed is None:
            return

        async def chunks():
            for c in self.streamed or []:
                yield c

        start_speech(chunks())

    async def handle_final_transcript(self, text: str, start_speech=None) -> VoiceReply:
        self.heard.append(text)
        self._maybe_stream(start_speech)
        return self.reply

    async def opening(self, start_speech=None) -> VoiceReply:
        self._maybe_stream(start_speech)
        return self.reply


def test_build_stt_defaults_to_saaras_v4() -> None:
    engine = build_stt(_settings(), ["FastAPI"])
    assert isinstance(engine, sarvam.STT)
    assert engine._opts.model == "saaras:v4"
    assert engine._opts.prompt and "FastAPI" in engine._opts.prompt


def test_build_stt_realtime_sends_keyterm_prompt() -> None:
    engine = build_stt(_settings(sarvam_stt_model="saaras:v3-realtime"), ["LiveKit", "pgvector"])
    assert isinstance(engine, sarvam.STTRealtime)
    assert "LiveKit, pgvector" in (engine._opts.prompt or "")


def test_build_tts_falls_back_to_versioned_bulbul() -> None:
    assert build_tts(_settings(sarvam_tts_model="bulbul"))._opts.model == "bulbul:v3"
    assert build_tts(_settings(sarvam_tts_model="bulbul:v2"))._opts.model == "bulbul:v2"


def test_build_tts_v4_gets_a_compatible_default_speaker() -> None:
    engine = build_tts(_settings(sarvam_tts_model="bulbul:v4-flash"))
    assert engine._opts.speaker == BULBUL_V4_DEFAULT_SPEAKER
    explicit = build_tts(_settings(sarvam_tts_model="bulbul:v4-flash", sarvam_tts_speaker="dev_en_conversational"))
    assert explicit._opts.speaker == "dev_en_conversational"


def test_turns_are_candidate_driven() -> None:
    assert TURN_HANDLING["turn_detection"] == "manual"
    assert TURN_HANDLING["interruption"] == {"enabled": False}


def test_speak_question_plays_through_and_keeps_session() -> None:
    session = FakeSession()
    speak(session, VoiceReply("Tell me about FastAPI."))  # type: ignore[arg-type]
    assert session.said == [("Tell me about FastAPI.", False)]
    assert session.shutdowns == []


def test_speak_closing_drains_then_shuts_down() -> None:
    session = FakeSession()
    speak(session, VoiceReply(CLOSING_LINE, done=True))  # type: ignore[arg-type]
    assert session.said == [(CLOSING_LINE, False)]
    assert session.shutdowns == [True]


def test_speak_nothing_for_empty_reply() -> None:
    session = FakeSession()
    speak(session, VoiceReply(None))  # type: ignore[arg-type]
    assert session.said == [] and session.shutdowns == []


def _agent_with(
    monkeypatch: pytest.MonkeyPatch, reply: VoiceReply, streamed: list[str] | None = None
):
    fake_session = FakeSession()
    controller = FakeController(reply, streamed)
    monkeypatch.setattr(GrillVoiceAgent, "session", property(lambda _self: fake_session))
    return GrillVoiceAgent(controller), controller, fake_session  # type: ignore[arg-type]


def test_user_turn_routes_to_grill_and_suppresses_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    agent, controller, session = _agent_with(monkeypatch, VoiceReply("What did you own?"))
    msg = ChatMessage(role="user", content=["I built the billing API"])
    with pytest.raises(StopResponse):
        asyncio.run(agent.on_user_turn_completed(ChatContext.empty(), msg))
    assert controller.heard == ["I built the billing API"]
    assert session.said == [("What did you own?", False)]


def test_user_turn_that_wraps_ends_session(monkeypatch: pytest.MonkeyPatch) -> None:
    agent, _, session = _agent_with(monkeypatch, VoiceReply(CLOSING_LINE, done=True))
    msg = ChatMessage(role="user", content=["that's all"])
    with pytest.raises(StopResponse):
        asyncio.run(agent.on_user_turn_completed(ChatContext.empty(), msg))
    assert session.shutdowns == [True]


def test_on_enter_speaks_opening(monkeypatch: pytest.MonkeyPatch) -> None:
    agent, _, session = _agent_with(monkeypatch, VoiceReply("Welcome — tell me about yourself."))
    asyncio.run(agent.on_enter())
    assert session.said == [("Welcome — tell me about yourself.", False)]


async def _drain(stream) -> list[str]:
    return [c async for c in stream]


def test_streamed_question_is_spoken_as_it_arrives(monkeypatch: pytest.MonkeyPatch) -> None:
    agent, _, session = _agent_with(
        monkeypatch, VoiceReply(None), streamed=["How did you ", "shard it?"]
    )
    msg = ChatMessage(role="user", content=["I sharded the ledger"])
    with pytest.raises(StopResponse):
        asyncio.run(agent.on_user_turn_completed(ChatContext.empty(), msg))
    assert len(session.said) == 1
    stream, allow_interruptions = session.said[0]
    assert allow_interruptions is False
    assert asyncio.run(_drain(stream)) == ["How did you ", "shard it?"]


def test_streamed_opening_is_spoken(monkeypatch: pytest.MonkeyPatch) -> None:
    agent, _, session = _agent_with(monkeypatch, VoiceReply(None), streamed=["Welcome."])
    asyncio.run(agent.on_enter())
    assert len(session.said) == 1
    assert asyncio.run(_drain(session.said[0][0])) == ["Welcome."]
