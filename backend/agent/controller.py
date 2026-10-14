"""Voice turn controller — bridges final STT transcripts to the DB-backed grill engine.

No LiveKit imports: the worker adapts speech I/O onto this; tests drive it directly.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InterviewSession, Turn
from app.services import grill as grill_svc
from app.services.scorer import schedule_turn_score

CLOSING_LINE = (
    "That's the end of our interview. Thanks for your time — "
    "your transcript has been saved."
)


@dataclass(frozen=True)
class VoiceReply:
    text: str | None
    done: bool = False


SpeechStarter = Callable[[AsyncIterator[str]], None]


class SpeechPipe:
    """Feeds a streamed question into one utterance, started on the first non-empty chunk."""

    def __init__(self, start: SpeechStarter) -> None:
        self._start = start
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._closed = False
        self.started = False

    def push(self, text: str) -> None:
        if not text or self._closed:
            return
        if not self.started:
            self.started = True
            self._start(self._chunks())
        self._queue.put_nowait(text)

    def close(self) -> None:
        if self.started and not self._closed:
            self._queue.put_nowait(None)
        self._closed = True

    async def _chunks(self) -> AsyncIterator[str]:
        while (chunk := await self._queue.get()) is not None:
            yield chunk


class VoiceGrillController:
    def __init__(
        self,
        session_id: uuid.UUID,
        session_factory: Callable[[], AsyncSession],
    ) -> None:
        self.session_id = session_id
        self._factory = session_factory

    async def _load(self, db: AsyncSession) -> InterviewSession | None:
        # Row lock serialises voice turns with concurrent text answers / End on the same session.
        result = await db.execute(
            select(InterviewSession)
            .where(InterviewSession.id == self.session_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def lexicon(self) -> dict[str, Any]:
        async with self._factory() as db:
            session = await db.get(InterviewSession, self.session_id)
            return dict(session.lexicon or {}) if session else {}

    async def opening(self, start_speech: SpeechStarter | None = None) -> VoiceReply:
        """First (or resumed) question to speak on join.

        With `start_speech`, a freshly generated question is spoken while it streams and the
        reply text is None (it is already playing)."""
        pipe = SpeechPipe(start_speech) if start_speech else None
        try:
            return await self._opening(pipe)
        finally:
            if pipe is not None:
                pipe.close()

    async def _opening(self, pipe: SpeechPipe | None) -> VoiceReply:
        async with self._factory() as db:
            session = await self._load(db)
            if session is None or session.status != "live":
                return VoiceReply(None, done=True)
            await grill_svc.begin_interview(db, session, sink=pipe)
            await db.commit()
            if pipe is not None and pipe.started:
                return VoiceReply(None)
            last = (
                await db.execute(
                    select(Turn)
                    .where(Turn.session_id == self.session_id, Turn.role == "agent")
                    .order_by(Turn.created_at.desc(), Turn.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            return VoiceReply(last.raw_text if last else None)

    async def handle_final_transcript(
        self, text: str, start_speech: SpeechStarter | None = None
    ) -> VoiceReply:
        """With `start_speech`, the next question is spoken while it streams (reply text None)."""
        text = (text or "").strip()
        if not text:
            return VoiceReply(None)
        pipe = SpeechPipe(start_speech) if start_speech else None
        try:
            return await self._answer(text, pipe)
        finally:
            if pipe is not None:
                pipe.close()

    async def _answer(self, text: str, pipe: SpeechPipe | None) -> VoiceReply:
        async with self._factory() as db:
            session = await self._load(db)
            if session is None or session.status != "live":
                return VoiceReply(None, done=True)
            user_turn, agent_turn = await grill_svc.submit_answer(db, session, text, sink=pipe)
            await db.commit()
            schedule_turn_score(user_turn.id)
            if session.status == "completed":
                from app.services.report_job import schedule_report_job

                schedule_report_job(session.id)
                return VoiceReply(CLOSING_LINE, done=True)
            if pipe is not None and pipe.started:
                return VoiceReply(None)
            return VoiceReply(agent_turn.raw_text if agent_turn else None)

    async def poll(self, now: datetime | None = None) -> VoiceReply | None:
        """Server-authoritative timer + external End. None → keep going."""
        now = now or datetime.now(timezone.utc)
        async with self._factory() as db:
            session = await self._load(db)
            if session is None or session.status != "live":
                return VoiceReply(None, done=True)
            ends = session.ends_at
            if ends is not None and ends.tzinfo is None:
                ends = ends.replace(tzinfo=timezone.utc)
            if ends is not None and now >= ends:
                await grill_svc.end_interview(db, session, reason="timer")
                await db.commit()
                from app.services.report_job import schedule_report_job

                schedule_report_job(session.id)
                return VoiceReply(CLOSING_LINE, done=True)
            return None

    async def on_disconnect(self) -> None:
        """Candidate left the room → wrap the session if still live."""
        async with self._factory() as db:
            session = await self._load(db)
            if session is not None and session.status == "live":
                await grill_svc.end_interview(db, session, reason="voice_disconnected")
                await db.commit()
                from app.services.report_job import schedule_report_job

                schedule_report_job(session.id)
