"""Phase 6 — assemble + prose + markdown job for session_reports."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import SessionLocal
from app.models import (
    Claim,
    Document,
    FrontierNode,
    InterviewSession,
    SessionReport,
    SessionResult,
    SessionTopic,
    Turn,
    TurnScore,
)
from app.services.report import (
    ReportAssemblyInput,
    ReportClaimInput,
    ReportCorrectionInput,
    ReportSessionMeta,
    ReportTopicInput,
    ReportTurnInput,
    assemble_report,
)
from app.services.report_markdown import render_report_markdown
from app.services.report_prose import fill_prose

log = structlog.get_logger()


async def ensure_report_pending(
    db: AsyncSession, session_id: uuid.UUID, *, force: bool = False
) -> SessionReport:
    """Idempotent: create pending row; optionally force regenerate even if ready."""
    row = (
        await db.execute(select(SessionReport).where(SessionReport.session_id == session_id))
    ).scalar_one_or_none()
    if row is None:
        row = SessionReport(session_id=session_id, status="pending")
        db.add(row)
        await db.flush()
        return row
    if force or row.status != "ready":
        row.status = "pending"
        row.report_json = None
        row.report_markdown = None
        await db.flush()
    return row


def schedule_report_job(session_id: uuid.UUID) -> None:
    """Fire-and-forget after the request/agent transaction commits."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        log.warning("report_schedule_no_loop", session_id=str(session_id))
        return
    loop.create_task(run_report_job(session_id))


async def load_assembly_input(db: AsyncSession, session: InterviewSession) -> ReportAssemblyInput:
    result = (
        await db.execute(select(SessionResult).where(SessionResult.session_id == session.id))
    ).scalar_one_or_none()
    if result is None:
        raise ValueError("session_results missing — finalize scoring first")

    topics = (
        await db.execute(
            select(SessionTopic)
            .where(SessionTopic.session_id == session.id)
            .options(selectinload(SessionTopic.frontier_nodes))
            .order_by(SessionTopic.priority.desc(), SessionTopic.title)
        )
    ).scalars().all()

    turns = (
        await db.execute(
            select(Turn)
            .where(Turn.session_id == session.id)
            .options(selectinload(Turn.score).selectinload(TurnScore.evidence))
            .order_by(Turn.created_at, Turn.id)
        )
    ).scalars().all()

    resume = await db.get(Document, session.resume_document_id) if session.resume_document_id else None
    jd = await db.get(Document, session.jd_document_id) if session.jd_document_id else None

    claim_ids = {t.claim_id for t in topics if t.claim_id}
    claims_rows: list[Claim] = []
    if claim_ids:
        claims_rows = list(
            (await db.execute(select(Claim).where(Claim.id.in_(claim_ids)))).scalars().all()
        )
    doc_types: dict[uuid.UUID, str] = {}
    for c in claims_rows:
        if c.document_id not in doc_types:
            doc = await db.get(Document, c.document_id)
            if doc:
                doc_types[c.document_id] = doc.doc_type

    settings = dict(session.settings or {})
    grill_meta = settings.get("_grill") if isinstance(settings.get("_grill"), dict) else {}
    wrap_reason = grill_meta.get("wrap_reason") if grill_meta else None

    evidence_by_topic: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for turn in turns:
        if turn.role != "user" or turn.topic_id is None or turn.score is None:
            continue
        for ev in turn.score.evidence or []:
            evidence_by_topic.setdefault(turn.topic_id, []).append(
                {
                    "chunk_id": str(ev.chunk_id),
                    "quote": ev.quote,
                    "source": ev.source,
                }
            )

    topic_inputs: list[ReportTopicInput] = []
    for t in topics:
        intents = sorted(
            {
                n.intent
                for n in (t.frontier_nodes or [])
                if isinstance(n, FrontierNode) and n.intent
            }
        )
        # de-dupe evidence quotes
        seen: set[str] = set()
        quotes: list[dict[str, Any]] = []
        for q in evidence_by_topic.get(t.id, []):
            key = f"{q['chunk_id']}|{q['quote']}"
            if key in seen:
                continue
            seen.add(key)
            quotes.append(q)
        topic_inputs.append(
            ReportTopicInput(
                topic_id=str(t.id),
                title=t.title,
                kind=t.kind,
                status=t.status,
                claim_id=str(t.claim_id) if t.claim_id else None,
                rollup_scores=dict(t.rollup_scores or {}),
                intents=intents,
                evidence_quotes=quotes,
            )
        )

    corrections: list[ReportCorrectionInput] = []
    for turn in turns:
        if turn.role != "user":
            continue
        reps: list[str] = []
        for c in turn.corrections or []:
            if isinstance(c, dict) and c.get("from") and c.get("to"):
                reps.append(f"{c['from']}→{c['to']}")
        if reps:
            corrections.append(
                ReportCorrectionInput(
                    raw=turn.raw_text,
                    normalized=turn.normalized_text or turn.raw_text,
                    replacements=reps,
                )
            )

    turn_inputs = [
        ReportTurnInput(
            topic_id=str(t.topic_id) if t.topic_id else None,
            role=t.role,
            text=(t.normalized_text or t.raw_text or "").strip(),
        )
        for t in turns
        if (t.normalized_text or t.raw_text or "").strip()
    ]

    duration = int(settings.get("duration_minutes") or settings.get("duration") or 15)
    return ReportAssemblyInput(
        meta=ReportSessionMeta(
            session_id=str(session.id),
            duration_minutes=duration,
            difficulty=str(settings.get("difficulty") or "medium"),
            seniority=str(settings.get("seniority") or "mid"),
            resume_filename=resume.original_filename if resume else None,
            jd_filename=jd.original_filename if jd else None,
            wrap_reason=str(wrap_reason) if wrap_reason else None,
        ),
        overall_score=result.overall_score,
        hire_signal=result.hire_signal,
        strengths=list(result.strengths or []),
        gaps=list(result.gaps or []),
        coverage_summary=dict(result.coverage_summary or {}),
        topics=topic_inputs,
        claims=[
            ReportClaimInput(
                claim_id=str(c.id),
                claim_type=c.claim_type,
                text=c.text,
                document_type=doc_types.get(c.document_id, "resume"),
            )
            for c in claims_rows
        ],
        turns=turn_inputs,
        corrections=corrections,
    )


async def run_report_job(session_id: uuid.UUID) -> None:
    async with SessionLocal() as db:
        session = await db.get(InterviewSession, session_id)
        if session is None:
            log.warning("report_job_missing_session", session_id=str(session_id))
            return
        if session.status != "completed":
            log.info(
                "report_job_skip_not_completed",
                session_id=str(session_id),
                status=session.status,
            )
            return

        row = await ensure_report_pending(db, session_id)
        if row.status == "ready" and row.report_json:
            return
        row.status = "pending"
        await db.commit()

        try:
            # re-load after commit
            session = await db.get(InterviewSession, session_id)
            assert session is not None
            assembled = assemble_report(await load_assembly_input(db, session))
            filled = await fill_prose(assembled)
            md = render_report_markdown(filled)
            row = (
                await db.execute(
                    select(SessionReport).where(SessionReport.session_id == session_id)
                )
            ).scalar_one()
            row.report_json = filled
            row.report_markdown = md
            row.status = "ready"
            await db.commit()
            log.info("report_ready", session_id=str(session_id))
        except Exception as exc:  # noqa: BLE001
            log.exception("report_failed", session_id=str(session_id), error=str(exc))
            await db.rollback()
            row = (
                await db.execute(
                    select(SessionReport).where(SessionReport.session_id == session_id)
                )
            ).scalar_one_or_none()
            if row is not None:
                row.status = "failed"
                row.report_json = None
                row.report_markdown = None
                await db.commit()
