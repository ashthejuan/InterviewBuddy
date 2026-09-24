"""ORM models matching PRD §9."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

EMBEDDING_DIMS = 384


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    documents: Mapped[list[Document]] = relationship(back_populates="user")
    sessions: Mapped[list[InterviewSession]] = relationship(back_populates="user")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("doc_type IN ('resume', 'jd')", name="ck_documents_doc_type"),
        CheckConstraint(
            "parse_status IN ('pending', 'processing', 'ready', 'failed')",
            name="ck_documents_parse_status",
        ),
        Index("ix_documents_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    doc_type: Mapped[str] = mapped_column(Text, nullable=False)
    r2_bucket: Mapped[str | None] = mapped_column(Text)
    r2_key: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str | None] = mapped_column(Text)
    byte_size: Mapped[int | None] = mapped_column(Integer)
    parse_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=sa_text("'pending'")
    )
    parse_error: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="documents")
    sections: Mapped[list[DocumentSection]] = relationship(back_populates="document")
    claims: Mapped[list[Claim]] = relationship(back_populates="document")


class DocumentSection(Base):
    __tablename__ = "document_sections"
    __table_args__ = (Index("ix_document_sections_document_id", "document_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("0"))

    document: Mapped[Document] = relationship(back_populates="sections")
    chunks: Mapped[list[DocumentChunk]] = relationship(back_populates="section")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_document_id", "document_id"),
        Index("ix_document_chunks_section_id", "section_id"),
        # HNSW added in migration (op.execute) — Vector index not portable via Index() alone.
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_sections.id", ondelete="CASCADE"), nullable=False
    )
    parent_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="SET NULL")
    )
    chunk_kind: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMS))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=sa_text("'{}'::jsonb")
    )

    section: Mapped[DocumentSection] = relationship(back_populates="chunks")


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (Index("ix_claims_document_id", "document_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    claim_type: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    measurability: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("0"))
    source_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default=sa_text("'{}'")
    )

    document: Mapped[Document] = relationship(back_populates="claims")


class InterviewSession(Base):
    __tablename__ = "interview_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('preparing', 'ready', 'live', 'completed', 'failed')",
            name="ck_interview_sessions_status",
        ),
        Index("ix_interview_sessions_user_id", "user_id"),
        Index("ix_interview_sessions_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    resume_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    jd_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'preparing'"))
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'::jsonb")
    )
    n_target: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lexicon: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="sessions")
    topics: Mapped[list[SessionTopic]] = relationship(back_populates="session")
    turns: Mapped[list[Turn]] = relationship(back_populates="session")
    result: Mapped[SessionResult | None] = relationship(back_populates="session")
    report: Mapped[SessionReport | None] = relationship(back_populates="session")


class SessionTopic(Base):
    __tablename__ = "session_topics"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned', 'active', 'scored', 'skipped')",
            name="ck_session_topics_status",
        ),
        Index("ix_session_topics_session_id_status", "session_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claims.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("0"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'planned'"))
    soft_cap_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa_text("210")
    )
    hard_cap_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa_text("330")
    )
    seconds_spent: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("0"))
    rollup_scores: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'::jsonb")
    )

    session: Mapped[InterviewSession] = relationship(back_populates="topics")
    frontier_nodes: Mapped[list[FrontierNode]] = relationship(back_populates="topic")


class FrontierNode(Base):
    __tablename__ = "frontier_nodes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('locked', 'available', 'in_progress', 'exhausted', 'abandoned')",
            name="ck_frontier_nodes_status",
        ),
        CheckConstraint(
            "question_mode IN ('parallel', 'direct', 'escalate')",
            name="ck_frontier_nodes_question_mode",
        ),
        Index("ix_frontier_nodes_session_id_status", "session_id", "status"),
        Index("ix_frontier_nodes_topic_id", "topic_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("session_topics.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("frontier_nodes.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'locked'"))
    prereqs: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default=sa_text("'{}'")
    )
    intent: Mapped[str | None] = mapped_column(Text)
    question_mode: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=sa_text("'parallel'")
    )
    max_followups: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("2"))
    followups_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("0"))
    depth_level: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("0"))

    topic: Mapped[SessionTopic] = relationship(back_populates="frontier_nodes")


class Turn(Base):
    __tablename__ = "turns"
    __table_args__ = (
        CheckConstraint("role IN ('agent', 'user')", name="ck_turns_role"),
        Index("ix_turns_session_id_created_at", "session_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("session_topics.id", ondelete="SET NULL")
    )
    frontier_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("frontier_nodes.id", ondelete="SET NULL")
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    corrections: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[InterviewSession] = relationship(back_populates="turns")
    score: Mapped[TurnScore | None] = relationship(back_populates="turn")


class TurnScore(Base):
    __tablename__ = "turn_scores"
    __table_args__ = (
        UniqueConstraint("turn_id", name="uq_turn_scores_turn_id"),
        CheckConstraint("correctness BETWEEN 0 AND 5", name="ck_turn_scores_correctness"),
        CheckConstraint("relevance BETWEEN 0 AND 5", name="ck_turn_scores_relevance"),
        CheckConstraint("depth BETWEEN 0 AND 5", name="ck_turn_scores_depth"),
        CheckConstraint("structure BETWEEN 0 AND 5", name="ck_turn_scores_structure"),
        CheckConstraint("honesty BETWEEN 0 AND 5", name="ck_turn_scores_honesty"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    turn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("turns.id", ondelete="CASCADE"), nullable=False
    )
    correctness: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    relevance: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    depth: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    structure: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    honesty: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    rationale: Mapped[str | None] = mapped_column(Text)
    flags: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'::jsonb")
    )

    turn: Mapped[Turn] = relationship(back_populates="score")
    evidence: Mapped[list[TurnEvidence]] = relationship(back_populates="turn_score")


class TurnEvidence(Base):
    __tablename__ = "turn_evidence"
    __table_args__ = (Index("ix_turn_evidence_turn_score_id", "turn_score_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    turn_score_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("turn_scores.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False
    )
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(Text)

    turn_score: Mapped[TurnScore] = relationship(back_populates="evidence")


class SessionResult(Base):
    __tablename__ = "session_results"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_session_results_session_id"),
        CheckConstraint(
            "hire_signal IN ('needs_work', 'mixed', 'solid', 'strong')",
            name="ck_session_results_hire_signal",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    overall_score: Mapped[float | None] = mapped_column(Float)
    hire_signal: Mapped[str | None] = mapped_column(Text)
    strengths: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'[]'::jsonb")
    )
    gaps: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'[]'::jsonb")
    )
    coverage_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[InterviewSession] = relationship(back_populates="result")


class SessionReport(Base):
    __tablename__ = "session_reports"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_session_reports_session_id"),
        CheckConstraint(
            "status IN ('pending', 'ready', 'failed')",
            name="ck_session_reports_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'pending'"))
    report_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    report_markdown: Mapped[str | None] = mapped_column(Text)
    r2_pdf_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    session: Mapped[InterviewSession] = relationship(back_populates="report")
