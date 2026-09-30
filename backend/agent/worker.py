"""LiveKit agent worker: Sarvam STT → deterministic correction → grill engine → Sarvam TTS.

Run from backend/:  uv run python -m agent.worker dev
The agent has no LLM of its own; every reply comes from the grill engine via the controller,
so LiveKit only owns transport, VAD, turn-taking and barge-in.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    ChatContext,
    ChatMessage,
    CloseEvent,
    CloseReason,
    JobContext,
    JobProcess,
    StopResponse,
    cli,
    stt,
    tts,
)
from livekit.plugins import sarvam, silero

from agent.controller import VoiceGrillController, VoiceReply
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.services.voice import (
    CANDIDATE_PREFIX,
    lexicon_keyterms,
    parse_job_metadata,
    stt_prompt,
)

log = structlog.get_logger()

SARVAM_REALTIME_MODEL = "saaras:v3-realtime"
TIMER_POLL_SECONDS = 5.0


def build_stt(settings: Settings, keyterms: list[str]) -> stt.STT:
    prompt = stt_prompt(keyterms)
    api_key = settings.sarvam_api_key or None
    if settings.sarvam_stt_model == SARVAM_REALTIME_MODEL:
        return sarvam.STTRealtime(language=settings.sarvam_language, prompt=prompt, api_key=api_key)
    # plugin 1.8 does not forward `prompt` for saaras:v4; lexicon repair still runs server-side
    return sarvam.STT(
        language=settings.sarvam_language,
        model=settings.sarvam_stt_model,
        prompt=prompt,
        api_key=api_key,
    )


def build_tts(settings: Settings) -> tts.TTS:
    model = settings.sarvam_tts_model if ":" in settings.sarvam_tts_model else "bulbul:v3"
    kwargs: dict[str, str] = {}
    if settings.sarvam_tts_speaker:
        kwargs["speaker"] = settings.sarvam_tts_speaker
    return sarvam.TTS(
        target_language_code=settings.sarvam_language,
        model=model,
        api_key=settings.sarvam_api_key or None,
        **kwargs,
    )


def speak(session: AgentSession, reply: VoiceReply) -> None:
    if reply.text:
        # The closing line is not interruptible so the candidate hears the wrap.
        session.say(reply.text, allow_interruptions=not reply.done)
    if reply.done:
        session.shutdown(drain=True)


class GrillVoiceAgent(Agent):
    def __init__(self, controller: VoiceGrillController) -> None:
        super().__init__(
            instructions="Speech I/O only; questions come from the InterviewBuddy grill engine."
        )
        self._controller = controller

    async def on_enter(self) -> None:
        speak(self.session, await self._controller.opening())

    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage
    ) -> None:
        reply = await self._controller.handle_final_transcript(new_message.text_content or "")
        speak(self.session, reply)
        raise StopResponse()


async def watch_timer(session: AgentSession, controller: VoiceGrillController) -> None:
    while True:
        await asyncio.sleep(TIMER_POLL_SECONDS)
        try:
            reply = await controller.poll()
        except Exception as exc:  # noqa: BLE001 — a DB blip must not kill the call
            log.warning("voice_timer_poll_failed", error=str(exc))
            continue
        if reply is not None:
            speak(session, reply)
            return


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


server = AgentServer()
server.setup_fnc = prewarm


@server.rtc_session(agent_name=get_settings().livekit_agent_name)
async def interview_agent(ctx: JobContext) -> None:
    settings = get_settings()
    try:
        session_id = parse_job_metadata(ctx.job.metadata)
    except ValueError as exc:
        log.warning("voice_bad_job_metadata", error=str(exc), room=ctx.room.name)
        ctx.shutdown(reason="bad job metadata")
        return
    ctx.log_context_fields = {"session_id": str(session_id), "room": ctx.room.name}

    controller = VoiceGrillController(session_id, SessionLocal)
    keyterms = lexicon_keyterms(await controller.lexicon())
    session = AgentSession(
        stt=build_stt(settings, keyterms),
        tts=build_tts(settings),
        vad=ctx.proc.userdata["vad"],
    )

    timer_task: asyncio.Task[None] | None = None
    candidate_left = False

    def on_participant_disconnected(participant: rtc.RemoteParticipant) -> None:
        nonlocal candidate_left
        if participant.identity.startswith(CANDIDATE_PREFIX):
            candidate_left = True

    def on_close(ev: CloseEvent) -> None:
        nonlocal candidate_left
        if ev.reason == CloseReason.PARTICIPANT_DISCONNECTED:
            candidate_left = True
        if ev.error is not None:
            log.warning("voice_session_error", error=str(ev.error), reason=ev.reason.value)
        ctx.shutdown(reason=f"agent session closed: {ev.reason.value}")

    async def on_shutdown() -> None:
        if timer_task is not None:
            timer_task.cancel()
        # Only the candidate leaving wraps the interview; an STT/TTS failure leaves it live
        # so the candidate can continue by typing or rejoin voice.
        if candidate_left:
            await controller.on_disconnect()

    ctx.room.on("participant_disconnected", on_participant_disconnected)
    session.on("close", on_close)
    ctx.add_shutdown_callback(on_shutdown)

    log.info(
        "voice_session_start",
        session_id=str(session_id),
        stt_model=settings.sarvam_stt_model,
        keyterms=len(keyterms),
    )
    await session.start(agent=GrillVoiceAgent(controller), room=ctx.room)
    timer_task = asyncio.create_task(watch_timer(session, controller))


if __name__ == "__main__":
    cli.run_app(server)
