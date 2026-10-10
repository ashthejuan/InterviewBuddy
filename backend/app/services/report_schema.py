"""Phase 6 — locked `report_json` contract (PRD §3A).

Deterministic assembly fills tables; LLM may only fill `prose` later.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "v1"

HireSignal = Literal["needs_work", "mixed", "solid", "strong"]
Coverage = Literal["grilled", "light", "skipped"]
InterviewOutcome = Literal[
    "supported",
    "partial",
    "contradicted",
    "unsupported",
    "not_discussed",
    "insufficient_evidence",
]


class ReportEvidenceQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    quote: str
    source: str | None = None


class SessionMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    duration_minutes: int
    difficulty: str
    seniority: str
    resume_filename: str | None = None
    jd_filename: str | None = None
    wrap_reason: str | None = None


class OverallSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hire_signal: HireSignal | None
    overall_score: float | None
    dims: dict[str, float] = Field(default_factory=dict)
    summary: str | None = None


class CoverageTopic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_id: str
    title: str
    kind: str
    coverage: Coverage


class CoverageMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planned_n: int
    counts: dict[str, int]
    jd_must: dict[str, int]
    topics: list[CoverageTopic]


class TopicNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_id: str
    title: str
    kind: str
    status: str
    coverage: Coverage
    composite: float | None
    dims: dict[str, float] | None
    intents: list[str] = Field(default_factory=list)
    flags: dict[str, Any] = Field(default_factory=dict)
    n_turns: int = 0
    evidence_quotes: list[ReportEvidenceQuote] = Field(default_factory=list)
    insufficient_evidence: bool = False


class ResultItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_id: str
    title: str
    kind: str
    score: float | None = None
    reason: str
    severity: str | None = None


class ResumeLinkedNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    claim_text: str
    claim_type: str
    topic_id: str
    topic_title: str
    interview_outcome: InterviewOutcome
    detail: str
    evidence_quotes: list[ReportEvidenceQuote] = Field(default_factory=list)


class JdAlignmentItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_id: str
    title: str
    coverage: Coverage
    composite: float | None = None


class JdAlignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    covered: list[JdAlignmentItem] = Field(default_factory=list)
    weak: list[JdAlignmentItem] = Field(default_factory=list)
    missing: list[JdAlignmentItem] = Field(default_factory=list)


class AppendixQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_id: str | None = None
    role: Literal["agent", "user"]
    text: str


class CorrectionHighlight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw: str
    normalized: str
    replacements: list[str] = Field(default_factory=list)


class Appendix(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_quotes: list[AppendixQuote] = Field(default_factory=list)
    correction_highlights: list[CorrectionHighlight] = Field(default_factory=list)


class ReportProse(BaseModel):
    """LLM-fillable slots only. Assembler leaves these empty/null."""

    model_config = ConfigDict(extra="forbid")

    summary: str | None = None
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class ReportJson(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["v1"]
    session_meta: SessionMeta
    overall_signal: OverallSignal
    coverage_map: CoverageMap
    topic_notes: list[TopicNote]
    strengths: list[ResultItem]
    gaps: list[ResultItem]
    resume_linked_notes: list[ResumeLinkedNote] = Field(default_factory=list)
    jd_alignment: JdAlignment | None = None
    appendix: Appendix = Field(default_factory=Appendix)
    prose: ReportProse = Field(default_factory=ReportProse)


def validate_report_json(data: dict[str, Any]) -> ReportJson:
    return ReportJson.model_validate(data)
