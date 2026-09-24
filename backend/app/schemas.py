"""Pydantic request/response schemas for Phase 1 CRUD."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


Difficulty = Literal["easy", "medium", "hard"]
Seniority = Literal["intern", "junior", "mid", "senior", "staff"]
SessionStatus = Literal["preparing", "ready", "live", "completed", "failed"]


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    name: str | None = None
    id: uuid.UUID | None = None  # allow seeding DEV_USER_ID


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionSettings(BaseModel):
    duration_minutes: int = Field(default=30, ge=5, le=90)
    difficulty: Difficulty = "medium"
    seniority: Seniority = "mid"


class SessionCreate(BaseModel):
    settings: SessionSettings = Field(default_factory=SessionSettings)
    user_id: uuid.UUID | None = None  # defaults to DEV_USER_ID
    resume_document_id: uuid.UUID | None = None
    jd_document_id: uuid.UUID | None = None


class SessionOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    status: SessionStatus
    settings: dict[str, Any]
    resume_document_id: uuid.UUID | None
    jd_document_id: uuid.UUID | None
    n_target: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


DocType = Literal["resume", "jd"]
ParseStatus = Literal["pending", "processing", "ready", "failed"]


class PasteDocumentIn(BaseModel):
    doc_type: DocType
    text: str = Field(min_length=1)


class DocumentOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    doc_type: DocType
    content_type: str | None
    original_filename: str | None
    byte_size: int | None
    parse_status: ParseStatus
    parse_error: str | None
    raw_text: str | None
    r2_bucket: str | None
    r2_key: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChunkOut(BaseModel):
    id: uuid.UUID
    chunk_kind: str
    content: str
    parent_chunk_id: uuid.UUID | None
    metadata: dict[str, Any]


class SectionOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str | None
    text: str
    ordinal: int
    chunks: list[ChunkOut] = Field(default_factory=list)
