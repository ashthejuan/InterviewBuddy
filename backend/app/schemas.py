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
    user_id: uuid.UUID | None = None  # ignored; JWT subject owns the session
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
    lexicon: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    ends_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AnswerIn(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


class TurnOut(BaseModel):
    id: uuid.UUID
    role: str
    raw_text: str
    normalized_text: str | None = None
    corrections: list[dict[str, Any]] = Field(default_factory=list)
    topic_id: uuid.UUID | None
    frontier_node_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class VoiceStatusOut(BaseModel):
    enabled: bool


class VoiceTokenOut(BaseModel):
    server_url: str
    room_name: str
    participant_identity: str
    token: str
    expires_at: datetime


class AnswerOut(BaseModel):
    session: SessionOut
    user_turn: TurnOut
    agent_turn: TurnOut | None = None


class TopicOut(BaseModel):
    id: uuid.UUID
    title: str
    kind: str
    priority: int
    status: str
    claim_id: uuid.UUID | None
    soft_cap_seconds: int
    hard_cap_seconds: int
    rollup_scores: dict[str, Any] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


HireSignal = Literal["needs_work", "mixed", "solid", "strong"]


class EvidenceOut(BaseModel):
    chunk_id: uuid.UUID
    quote: str
    source: str | None

    model_config = {"from_attributes": True}


class TurnScoreOut(BaseModel):
    turn_id: uuid.UUID
    topic_id: uuid.UUID | None
    answer: str
    correctness: int
    relevance: int
    depth: int
    structure: int
    honesty: int
    confidence: float | None
    rationale: str | None
    flags: dict[str, Any]
    evidence: list[EvidenceOut] = Field(default_factory=list)


class SessionResultOut(BaseModel):
    session_id: uuid.UUID
    overall_score: float | None
    hire_signal: HireSignal | None
    strengths: list[dict[str, Any]]
    gaps: list[dict[str, Any]]
    coverage_summary: dict[str, Any]
    topics: list[TopicOut]
    turn_scores: list[TurnScoreOut]


ReportStatus = Literal["pending", "ready", "failed"]


class SessionReportOut(BaseModel):
    session_id: uuid.UUID
    status: ReportStatus
    report_json: dict[str, Any] | None = None
    report_markdown: str | None = None
    r2_pdf_key: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class TranscriptExportOut(BaseModel):
    path: str
    filename: str
    session_id: uuid.UUID


class FrontierNodeOut(BaseModel):
    id: uuid.UUID
    topic_id: uuid.UUID
    status: str
    intent: str | None
    question_mode: str
    depth_level: int
    parent_id: uuid.UUID | None

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
    has_embedding: bool = False


class SectionOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str | None
    text: str
    ordinal: int
    chunks: list[ChunkOut] = Field(default_factory=list)
