"""Async document prep: extract → normalize → chunk → embed → maybe finalize session."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Document, InterviewSession
from app.services.extract import ExtractError, extract_bytes
from app.services.finalize import embed_document_chunks, maybe_finalize_session
from app.services.normalize import normalize_text
from app.services.persist_chunks import persist_sections_and_chunks

log = structlog.get_logger()


async def run_extract_job(document_id: uuid.UUID, data: bytes, kind: str) -> None:
    async with SessionLocal() as db:
        doc = await db.get(Document, document_id)
        if doc is None:
            log.warning("extract_job_missing_doc", document_id=str(document_id))
            return

        doc.parse_status = "processing"
        await db.commit()

        try:
            if kind == "paste":
                text = data.decode("utf-8")
            else:
                text = extract_bytes(data, kind=kind)
            normalized = normalize_text(text)
            doc.raw_text = normalized
            n_sections, n_chunks = await persist_sections_and_chunks(
                db, doc, text=normalized
            )
            n_embedded = await embed_document_chunks(db, document_id)
            doc.parse_status = "ready"
            doc.parse_error = None
            log.info(
                "extract_ready",
                document_id=str(document_id),
                sections=n_sections,
                chunks=n_chunks,
                embedded=n_embedded,
            )
        except ExtractError as exc:
            doc.parse_status = "failed"
            doc.parse_error = str(exc)
            doc.raw_text = None
            log.info("extract_failed", document_id=str(document_id), error=str(exc))
        except Exception as exc:  # noqa: BLE001
            doc.parse_status = "failed"
            doc.parse_error = f"unexpected extract error: {exc}"
            doc.raw_text = None
            log.exception("extract_unexpected", document_id=str(document_id))

        await db.commit()

        # Link doc → session(s) and finalize when resume (+ optional JD) ready
        session_ids = await _sessions_for_document(db, document_id)
        for sid in session_ids:
            try:
                await maybe_finalize_session(db, sid)
                await db.commit()
            except Exception:  # noqa: BLE001
                await db.rollback()
                log.exception("finalize_failed", session_id=str(sid))
                session = await db.get(InterviewSession, sid)
                if session is not None and session.status == "preparing":
                    session.status = "failed"
                    await db.commit()


async def _sessions_for_document(
    db, document_id: uuid.UUID
) -> list[uuid.UUID]:
    result = await db.execute(
        select(InterviewSession.id).where(
            (InterviewSession.resume_document_id == document_id)
            | (InterviewSession.jd_document_id == document_id)
        )
    )
    return list(result.scalars().all())
