"""Async document prep: extract + normalize into documents.raw_text."""

from __future__ import annotations

import uuid

import structlog

from app.db import SessionLocal
from app.models import Document
from app.services.extract import ExtractError, extract_bytes
from app.services.normalize import normalize_text

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
            doc.raw_text = normalize_text(text)
            doc.parse_status = "ready"
            doc.parse_error = None
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
