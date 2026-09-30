"""Unit: LiveKit worker adapters — STT/TTS selection, speak(), user-turn hook (Phase 5)."""

from __future__ import annotations

import asyncio

import pytest
from livekit.agents import ChatContext, ChatMessage, StopResponse
from livekit.plugins import sarvam

from agent.controller import CLOSING_LINE, VoiceReply
from agent.worker import GrillVoiceAgent, build_stt, build_tts, speak
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
    def __init__(self, reply: VoiceReply) -> None:
        self.reply = reply
        self.heard: list[str] = []

    async def handle_final_transcript(self, text: str) -> VoiceReply:
        self.heard.append(text)
        return self.reply

    async def opening(self) -> VoiceReply:
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


def test_speak_question_is_interruptible_and_keeps_session() -> None:
    session = FakeSession()
    speak(session, VoiceReply("Tell me about FastAPI."))  # type: ignore[arg-type]
    assert session.said == [("Tell me about FastAPI.", True)]
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


def _agent_with(monkeypatch: pytest.MonkeyPatch, reply: VoiceReply):
    fake_session = FakeSession()
    controller = FakeController(reply)
    monkeypatch.setattr(GrillVoiceAgent, "session", property(lambda _self: fake_session))
    return GrillVoiceAgent(controller), controller, fake_session  # type: ignore[arg-type]


def test_user_turn_routes_to_grill_and_suppresses_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    agent, controller, session = _agent_with(monkeypatch, VoiceReply("What did you own?"))
    msg = ChatMessage(role="user", content=["I built the billing API"])
    with pytest.raises(StopResponse):
        asyncio.run(agent.on_user_turn_completed(ChatContext.empty(), msg))
    assert controller.heard == ["I built the billing API"]
    assert session.said == [("What did you own?", True)]


def test_user_turn_that_wraps_ends_session(monkeypatch: pytest.MonkeyPatch) -> None:
    agent, _, session = _agent_with(monkeypatch, VoiceReply(CLOSING_LINE, done=True))
    msg = ChatMessage(role="user", content=["that's all"])
    with pytest.raises(StopResponse):
        asyncio.run(agent.on_user_turn_completed(ChatContext.empty(), msg))
    assert session.shutdowns == [True]


def test_on_enter_speaks_opening(monkeypatch: pytest.MonkeyPatch) -> None:
    agent, _, session = _agent_with(monkeypatch, VoiceReply("Welcome — tell me about yourself."))
    asyncio.run(agent.on_enter())
    assert session.said == [("Welcome — tell me about yourself.", True)]
