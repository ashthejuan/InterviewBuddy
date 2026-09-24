"""Persist section parse + parent–child chunks after extract."""

from __future__ import annotations

import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk, DocumentSection
from app.services.chunk import chunk_section
from app.services.sections import parse_sections


async def persist_sections_and_chunks(
    db: AsyncSession,
    doc: Document,
    *,
    text: str,
) -> tuple[int, int]:
    """Replace any prior sections/chunks for this document. Returns (sections, chunks)."""
    # Children first (self-FK parent_chunk_id), then sections
    await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    await db.execute(delete(DocumentSection).where(DocumentSection.document_id == doc.id))
    await db.flush()

    parsed = parse_sections(text, doc_type=doc.doc_type)
    section_count = 0
    chunk_count = 0

    for ps in parsed:
        section = DocumentSection(
            id=uuid.uuid4(),
            document_id=doc.id,
            kind=ps.kind,
            title=ps.title,
            text=ps.text,
            ordinal=ps.ordinal,
        )
        db.add(section)
        await db.flush()
        section_count += 1

        chunks = chunk_section(ps, doc_type=doc.doc_type)
        created: list[DocumentChunk] = []
        for pc in chunks:
            row = DocumentChunk(
                id=uuid.uuid4(),
                document_id=doc.id,
                section_id=section.id,
                parent_chunk_id=None,
                chunk_kind=pc.chunk_kind,
                content=pc.content,
                embedding=None,
                metadata_=dict(pc.metadata),
            )
            db.add(row)
            await db.flush()
            created.append(row)
            chunk_count += 1

        # Second pass: wire parent_chunk_id from parent_index
        for i, pc in enumerate(chunks):
            if pc.parent_index is None:
                continue
            if pc.parent_index < 0 or pc.parent_index >= len(created):
                continue
            created[i].parent_chunk_id = created[pc.parent_index].id

    return section_count, chunk_count
