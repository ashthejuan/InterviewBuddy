"""DB-backed grill orchestration — wraps MemSession engine (Slice A)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models import FrontierNode, InterviewSession, SessionTopic, Turn
from app.services.grill_engine import (
    MemNode,
    MemSession,
    MemTopic,
    MemTurn,
    answer as eng_answer,
    begin as eng_begin,
    end as eng_end,
)
from app.services.grill_questions import generate_question
from app.services.scorer import (
    finalize_session_results,
    persist_turn_score,
    refresh_topic_rollup,
    score_answer,
)
from app.services.scoring import score_signal
from app.services.transcript_correct import correct_transcript


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _grill_meta(session: InterviewSession) -> dict[str, Any]:
    settings = dict(session.settings or {})
    meta = settings.get("_grill")
    return dict(meta) if isinstance(meta, dict) else {}


def _set_grill_meta(session: InterviewSession, meta: dict[str, Any]) -> None:
    settings = dict(session.settings or {})
    settings["_grill"] = meta
    session.settings = settings
    flag_modified(session, "settings")


async def _load_mem(db: AsyncSession, session: InterviewSession) -> MemSession:
    topics_r = await db.execute(
        select(SessionTopic).where(SessionTopic.session_id == session.id)
    )
    nodes_r = await db.execute(
        select(FrontierNode).where(FrontierNode.session_id == session.id)
    )
    topics = [
        MemTopic(
            id=str(t.id),
            title=t.title,
            kind=t.kind,
            priority=t.priority,
            status=t.status,
            soft_cap_seconds=t.soft_cap_seconds,
            hard_cap_seconds=t.hard_cap_seconds,
            seconds_spent=t.seconds_spent,
        )
        for t in topics_r.scalars().all()
    ]
    nodes = [
        MemNode(
            id=str(n.id),
            topic_id=str(n.topic_id),
            intent=n.intent or "",
            question_mode=n.question_mode,
            status=n.status,
            max_followups=n.max_followups,
            followups_used=n.followups_used,
        )
        for n in nodes_r.scalars().all()
    ]
    now = _now()
    if session.ends_at is not None:
        ends = session.ends_at
        if ends.tzinfo is None:
            ends = ends.replace(tzinfo=timezone.utc)
        time_left = max(0, int((ends - now).total_seconds()))
    else:
        time_left = 0

    meta = _grill_meta(session)
    mem = MemSession(
        status=session.status,
        topics=topics,
        nodes=nodes,
        time_left_seconds=time_left,
        wrap_reason=meta.get("wrap_reason"),
        active_topic_id=meta.get("active_topic_id"),
        active_node_id=meta.get("active_node_id"),
    )
    return mem


async def _persist_mem(
    db: AsyncSession,
    session: InterviewSession,
    mem: MemSession,
    *,
    new_turns: list[MemTurn],
) -> list[Turn]:
    topic_by_id = {str(t.id): t for t in (
        await db.execute(select(SessionTopic).where(SessionTopic.session_id == session.id))
    ).scalars().all()}
    node_by_id = {str(n.id): n for n in (
        await db.execute(select(FrontierNode).where(FrontierNode.session_id == session.id))
    ).scalars().all()}

    for mt in mem.topics:
        row = topic_by_id.get(mt.id)
        if row is None:
            continue
        row.status = mt.status
        row.seconds_spent = mt.seconds_spent

    for mn in mem.nodes:
        row = node_by_id.get(mn.id)
        if row is None:
            continue
        row.status = mn.status
        row.followups_used = mn.followups_used

    session.status = mem.status
    meta = _grill_meta(session)
    meta["active_topic_id"] = mem.active_topic_id
    meta["active_node_id"] = mem.active_node_id
    if mem.wrap_reason:
        meta["wrap_reason"] = mem.wrap_reason
    # topic_started_at is owned by callers (begin / answer); do not drop it here
    _set_grill_meta(session, meta)

    persisted: list[Turn] = []
    # Explicit, strictly increasing stamps: DB now() is per-transaction, so a user turn and
    # its agent reply would otherwise tie and sort arbitrarily.
    stamp = _now()
    for idx, nt in enumerate(new_turns):
        turn = Turn(
            id=uuid.uuid4(),
            session_id=session.id,
            created_at=stamp + timedelta(microseconds=idx),
            topic_id=uuid.UUID(nt.topic_id) if nt.topic_id else None,
            frontier_node_id=uuid.UUID(nt.node_id) if nt.node_id else None,
            role=nt.role,
            raw_text=nt.text,
            normalized_text=nt.text,
        )
        db.add(turn)
        persisted.append(turn)

    await db.flush()
    return persisted


def _topic_seconds(session: InterviewSession, now: datetime) -> int:
    meta = _grill_meta(session)
    started = meta.get("topic_started_at")
    if not started:
        return 0
    try:
        ts = datetime.fromisoformat(started)
    except ValueError:
        return 0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0, int((now - ts).total_seconds()))


async def _rewrite_agent_turns(
    db: AsyncSession,
    session: InterviewSession,
    mem: MemSession,
    new_turns: list[MemTurn],
    *,
    prior_user_answer: str | None,
) -> None:
    for nt in new_turns:
        if nt.role != "agent":
            continue
        topic = next((t for t in mem.topics if t.id == nt.topic_id), None)
        node = next((n for n in mem.nodes if n.id == nt.node_id), None)
        if topic is None or node is None:
            continue
        followup = node.followups_used > 0
        nt.text = await generate_question(
            db,
            session,
            title=topic.title,
            intent=node.intent,
            mode=node.question_mode if not followup else (
                "escalate" if node.followups_used > 1 else node.question_mode
            ),
            followup=followup,
            prior_user_answer=prior_user_answer if followup else None,
            directive=nt.directive,
        )


async def _last_agent_text(db: AsyncSession, session_id: uuid.UUID) -> str:
    row = (
        await db.execute(
            select(Turn.raw_text)
            .where(Turn.session_id == session_id, Turn.role == "agent")
            .order_by(Turn.created_at.desc(), Turn.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return row or ""


async def begin_interview(db: AsyncSession, session: InterviewSession) -> Turn | None:
    """Activate first topic and persist opening agent question. Idempotent if turns exist."""
    existing = await db.execute(
        select(Turn).where(Turn.session_id == session.id).limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        return None

    mem = await _load_mem(db, session)
    before = len(mem.turns)
    eng_begin(mem)
    new_turns = mem.turns[before:]
    await _rewrite_agent_turns(
        db, session, mem, new_turns, prior_user_answer=None
    )
    now = _now()
    meta = _grill_meta(session)
    meta["topic_started_at"] = now.isoformat()
    meta["active_topic_id"] = mem.active_topic_id
    meta["active_node_id"] = mem.active_node_id
    _set_grill_meta(session, meta)

    persisted = await _persist_mem(db, session, mem, new_turns=new_turns)
    return persisted[-1] if persisted else None


async def submit_answer(
    db: AsyncSession, session: InterviewSession, text: str
) -> tuple[Turn, Turn | None]:
    """Persist user answer + next agent turn (or wrap). Returns (user_turn, agent_turn|None).

    `text` is the raw answer (typed or STT final); grill, retrieval and scoring use the
    lexicon-corrected form. The rubric score is computed first so its flags can steer the frontier.
    """
    now = _now()
    normalized, corrections = correct_transcript(text, session.lexicon)
    mem = await _load_mem(db, session)
    seconds = _topic_seconds(session, now)

    scored_topic: SessionTopic | None = None
    draft = None
    signal = None
    if mem.active_topic_id:
        scored_topic = await db.get(SessionTopic, uuid.UUID(mem.active_topic_id))
    if scored_topic is not None:
        node = next((n for n in mem.nodes if n.id == mem.active_node_id), None)
        draft = await score_answer(
            db,
            session,
            scored_topic,
            intent=(node.intent if node else "") or scored_topic.title,
            question=await _last_agent_text(db, session.id),
            answer=normalized,
        )
        signal = score_signal(draft, kind=scored_topic.kind)

    before = len(mem.turns)
    next_q = eng_answer(mem, normalized, seconds_on_topic=seconds, signal=signal)
    new_turns = mem.turns[before:]
    await _rewrite_agent_turns(
        db, session, mem, new_turns, prior_user_answer=normalized
    )

    meta = _grill_meta(session)
    if mem.status == "completed":
        meta["wrap_reason"] = mem.wrap_reason
        meta.pop("topic_started_at", None)
    elif next_q is not None:
        # New question — if topic changed, reset topic clock
        prev_topic = meta.get("active_topic_id")
        if mem.active_topic_id != prev_topic:
            meta["topic_started_at"] = now.isoformat()
        meta["active_topic_id"] = mem.active_topic_id
        meta["active_node_id"] = mem.active_node_id
    agent_directives = [t.directive for t in new_turns if t.role == "agent"]
    meta["last_score_signal"] = signal
    meta["last_directive"] = agent_directives[-1] if agent_directives else None
    meta["last_exit_reason"] = mem.last_exit_reason
    _set_grill_meta(session, meta)

    persisted = await _persist_mem(db, session, mem, new_turns=new_turns)
    user_turn = next(t for t in persisted if t.role == "user")
    user_turn.raw_text = text
    user_turn.normalized_text = normalized
    user_turn.corrections = corrections
    if draft is not None and scored_topic is not None:
        persist_turn_score(db, user_turn, draft)
        await refresh_topic_rollup(db, scored_topic)
    if mem.status == "completed":
        await finalize_session_results(db, session)
    agent_turns = [t for t in persisted if t.role == "agent"]
    agent_turn = agent_turns[-1] if agent_turns else None
    return user_turn, agent_turn


async def end_interview(
    db: AsyncSession, session: InterviewSession, *, reason: str = "user_ended"
) -> None:
    mem = await _load_mem(db, session)
    if mem.status != "completed":
        eng_end(mem, reason=reason)
    await _persist_mem(db, session, mem, new_turns=[])
    meta = _grill_meta(session)
    meta["wrap_reason"] = mem.wrap_reason or reason
    meta.pop("topic_started_at", None)
    _set_grill_meta(session, meta)
    await finalize_session_results(db, session)
