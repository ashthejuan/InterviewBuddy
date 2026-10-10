"""Voice turn controller — bridges final STT transcripts to the DB-backed grill engine.

No LiveKit imports: the worker adapts speech I/O onto this; tests drive it directly.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InterviewSession, Turn
from app.services import grill as grill_svc

CLOSING_LINE = (
    "That's the end of our interview. Thanks for your time — "
    "your transcript has been saved."
)


@dataclass(frozen=True)
class VoiceReply:
    text: str | None
    done: bool = False


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

    async def opening(self) -> VoiceReply:
        """First (or resumed) question to speak on join."""
        async with self._factory() as db:
            session = await self._load(db)
            if session is None or session.status != "live":
                return VoiceReply(None, done=True)
            await grill_svc.begin_interview(db, session)
            await db.commit()
            last = (
                await db.execute(
                    select(Turn)
                    .where(Turn.session_id == self.session_id, Turn.role == "agent")
                    .order_by(Turn.created_at.desc(), Turn.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            return VoiceReply(last.raw_text if last else None)

    async def handle_final_transcript(self, text: str) -> VoiceReply:
        text = (text or "").strip()
        if not text:
            return VoiceReply(None)
        async with self._factory() as db:
            session = await self._load(db)
            if session is None or session.status != "live":
                return VoiceReply(None, done=True)
            _, agent_turn = await grill_svc.submit_answer(db, session, text)
            await db.commit()
            if session.status == "completed":
                from app.services.report_job import schedule_report_job

                schedule_report_job(session.id)
                return VoiceReply(CLOSING_LINE, done=True)
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
