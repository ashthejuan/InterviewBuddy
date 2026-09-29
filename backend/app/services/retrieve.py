"""pgvector retrieval for grill turns — children + parent expand."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DocumentChunk, InterviewSession
from app.services.embed import embed_texts
from app.services.grill_prompt import RetrievedChunk


async def retrieve_for_session(
    db: AsyncSession,
    session: InterviewSession,
    query: str,
    *,
    limit: int = 5,
) -> list[RetrievedChunk]:
    q = (query or "").strip()
    if not q:
        return []

    doc_ids = [
        d
        for d in (session.resume_document_id, session.jd_document_id)
        if d is not None
    ]
    if not doc_ids:
        return []

    vector = embed_texts([q])[0]
    result = await db.execute(
        select(DocumentChunk)
        .where(
            DocumentChunk.document_id.in_(doc_ids),
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(DocumentChunk.embedding.cosine_distance(vector))
        .limit(limit)
    )
    children = list(result.scalars().all())
    if not children:
        return []

    parent_ids = [c.parent_chunk_id for c in children if c.parent_chunk_id]
    parents: dict[uuid.UUID, DocumentChunk] = {}
    if parent_ids:
        prow = await db.execute(
            select(DocumentChunk).where(DocumentChunk.id.in_(parent_ids))
        )
        parents = {p.id: p for p in prow.scalars().all()}

    out: list[RetrievedChunk] = []
    for c in children:
        parent = parents.get(c.parent_chunk_id) if c.parent_chunk_id else None
        out.append(
            RetrievedChunk(
                id=c.id,
                content=c.content,
                parent_content=parent.content if parent else None,
            )
        )
    return out
