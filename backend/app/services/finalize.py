"""Finalize session prep: claims → lexicon → topics/frontier → ready."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Claim,
    Document,
    DocumentChunk,
    DocumentSection,
    FrontierNode,
    InterviewSession,
    SessionTopic,
)
from app.services.claims import ChunkRef, extract_claims
from app.services.embed import embed_texts
from app.services.lexicon import build_lexicon
from app.services.topics import ClaimSeed, plan_topics

log = structlog.get_logger()


async def embed_document_chunks(db: AsyncSession, document_id: uuid.UUID) -> int:
    """Embed child chunks; parents with no children get embedded as fallback."""
    result = await db.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )
    chunks = list(result.scalars().all())
    if not chunks:
        return 0

    children = [c for c in chunks if c.parent_chunk_id is not None]
    if not children:
        # no children → embed parents
        targets = [c for c in chunks if c.parent_chunk_id is None]
    else:
        targets = children

    vectors = embed_texts([c.content for c in targets])
    for chunk, vec in zip(targets, vectors, strict=True):
        chunk.embedding = vec
    await db.flush()
    return len(targets)


async def maybe_finalize_session(db: AsyncSession, session_id: uuid.UUID) -> None:
    session = await db.get(InterviewSession, session_id)
    if session is None:
        return
    if session.status in ("ready", "live", "completed"):
        return

    resume = (
        await db.get(Document, session.resume_document_id)
        if session.resume_document_id
        else None
    )
    if resume is None:
        return

    if resume.parse_status == "failed":
        session.status = "failed"
        await db.flush()
        log.info("session_failed_resume", session_id=str(session_id))
        return
    if resume.parse_status != "ready":
        return

    jd = (
        await db.get(Document, session.jd_document_id) if session.jd_document_id else None
    )
    if jd is not None:
        if jd.parse_status == "failed":
            session.status = "failed"
            await db.flush()
            log.info("session_failed_jd", session_id=str(session_id))
            return
        if jd.parse_status != "ready":
            return

    docs = [resume] + ([jd] if jd else [])
    await _rebuild_claims_lexicon_topics(db, session, docs)
    session.status = "ready"
    await db.flush()
    log.info(
        "session_ready",
        session_id=str(session_id),
        n_target=session.n_target,
    )


async def _rebuild_claims_lexicon_topics(
    db: AsyncSession,
    session: InterviewSession,
    docs: list[Document],
) -> None:
    # Clear prior topics/frontier + claims for these docs
    await db.execute(delete(FrontierNode).where(FrontierNode.session_id == session.id))
    await db.execute(delete(SessionTopic).where(SessionTopic.session_id == session.id))
    for doc in docs:
        await db.execute(delete(Claim).where(Claim.document_id == doc.id))
    await db.flush()

    all_claim_texts: list[str] = []
    all_chunk_texts: list[str] = []
    jd_seeds: list[ClaimSeed] = []
    claim_seeds: list[ClaimSeed] = []

    for doc in docs:
        chunk_rows = await _child_chunk_refs(db, doc.id)
        all_chunk_texts.extend(c.content for c in chunk_rows)
        drafts = await extract_claims(chunk_rows)
        for d in drafts:
            claim = Claim(
                id=uuid.uuid4(),
                document_id=doc.id,
                claim_type=d.claim_type,
                text=d.text,
                measurability=d.measurability,
                priority=d.priority,
                source_chunk_ids=d.source_chunk_ids,
            )
            db.add(claim)
            await db.flush()
            all_claim_texts.append(d.text)
            seed = ClaimSeed(
                claim_id=claim.id,
                title=d.text[:120],
                kind="jd_must" if doc.doc_type == "jd" else "claim",
                priority=d.priority + (50 if doc.doc_type == "jd" else 0),
                measurable=(d.measurability == "high" or d.claim_type == "metric"),
            )
            if doc.doc_type == "jd":
                jd_seeds.append(seed)
            else:
                claim_seeds.append(seed)

    session.lexicon = build_lexicon(
        claim_texts=all_claim_texts, chunk_texts=all_chunk_texts
    )

    duration = int((session.settings or {}).get("duration_minutes", 30))
    plan = plan_topics(
        duration_minutes=duration, jd_seeds=jd_seeds, claim_seeds=claim_seeds
    )
    session.n_target = plan.n_target

    for pt in plan.topics:
        topic = SessionTopic(
            id=uuid.uuid4(),
            session_id=session.id,
            claim_id=pt.claim_id,
            title=pt.title,
            kind=pt.kind,
            priority=pt.priority,
            status="planned",
            soft_cap_seconds=pt.soft_cap_seconds,
            hard_cap_seconds=pt.hard_cap_seconds,
        )
        db.add(topic)
        await db.flush()
        db.add(
            FrontierNode(
                id=uuid.uuid4(),
                session_id=session.id,
                topic_id=topic.id,
                parent_id=None,
                status="locked",
                intent=pt.title,
                question_mode=pt.question_mode,
                depth_level=0,
            )
        )
    await db.flush()


async def _child_chunk_refs(db: AsyncSession, document_id: uuid.UUID) -> list[ChunkRef]:
    result = await db.execute(
        select(DocumentChunk, DocumentSection.kind)
        .join(DocumentSection, DocumentSection.id == DocumentChunk.section_id)
        .where(DocumentChunk.document_id == document_id)
        .options()
    )
    rows = result.all()
    children = [
        ChunkRef(id=chunk.id, content=chunk.content, section_kind=kind)
        for chunk, kind in rows
        if chunk.parent_chunk_id is not None
    ]
    if children:
        return children
    return [
        ChunkRef(id=chunk.id, content=chunk.content, section_kind=kind)
        for chunk, kind in rows
    ]
