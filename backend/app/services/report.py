"""Phase 6 — deterministic report assembly from scored session data (no LLM)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.report_schema import SCHEMA_VERSION, validate_report_json
from app.services.scoring import STRENGTH_MIN, GAP_WEAK

_MAX_QUOTE_CHARS = 240
_MAX_DETAIL_CHARS = 280
_MAX_APPENDIX_QUOTES = 8
_MAX_CORRECTIONS = 10


@dataclass(frozen=True)
class ReportSessionMeta:
    session_id: str
    duration_minutes: int
    difficulty: str
    seniority: str
    resume_filename: str | None = None
    jd_filename: str | None = None
    wrap_reason: str | None = None


@dataclass(frozen=True)
class ReportTopicInput:
    topic_id: str
    title: str
    kind: str
    status: str
    claim_id: str | None
    rollup_scores: dict[str, Any]
    intents: list[str] = field(default_factory=list)
    evidence_quotes: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ReportClaimInput:
    claim_id: str
    claim_type: str
    text: str
    document_type: str  # resume | jd


@dataclass(frozen=True)
class ReportTurnInput:
    topic_id: str | None
    role: str
    text: str


@dataclass(frozen=True)
class ReportCorrectionInput:
    raw: str
    normalized: str
    replacements: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReportAssemblyInput:
    meta: ReportSessionMeta
    overall_score: float | None
    hire_signal: str | None
    strengths: list[dict[str, Any]]
    gaps: list[dict[str, Any]]
    coverage_summary: dict[str, Any]
    topics: list[ReportTopicInput]
    claims: list[ReportClaimInput] = field(default_factory=list)
    turns: list[ReportTurnInput] = field(default_factory=list)
    corrections: list[ReportCorrectionInput] = field(default_factory=list)


def _clip(text: str, n: int) -> str:
    text = (text or "").strip()
    if len(text) <= n:
        return text
    return text[: n - 1].rstrip() + "…"


def _coverage(rollup: dict[str, Any]) -> str:
    cov = rollup.get("coverage") or "skipped"
    return cov if cov in ("grilled", "light", "skipped") else "skipped"


def _insufficient(rollup: dict[str, Any]) -> bool:
    n_turns = int(rollup.get("n_turns") or 0)
    return rollup.get("composite") is None or n_turns == 0


def _normalize_quotes(quotes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for q in quotes:
        chunk_id = q.get("chunk_id")
        quote = (q.get("quote") or "").strip()
        if not chunk_id or not quote:
            continue
        out.append(
            {
                "chunk_id": str(chunk_id),
                "quote": _clip(quote, _MAX_QUOTE_CHARS),
                "source": q.get("source"),
            }
        )
    return out


def _answer_for_topic(turns: list[ReportTurnInput], topic_id: str) -> str:
    parts = [t.text for t in turns if t.topic_id == topic_id and t.role == "user" and t.text.strip()]
    return _clip(" ".join(parts), _MAX_DETAIL_CHARS)


def _interview_outcome(rollup: dict[str, Any]) -> tuple[str, str]:
    """Deterministic resume↔interview outcome + short detail."""
    if _insufficient(rollup):
        return "insufficient_evidence", "Topic was not scored — no interview evidence."

    flags = rollup.get("flags") or {}
    if flags.get("bluff") or flags.get("contradiction"):
        return "contradicted", "Answer conflicted with or overstated resume evidence."

    coverage = _coverage(rollup)
    if coverage == "skipped":
        return "not_discussed", "Topic was skipped or ended without a scorable answer."

    composite = rollup.get("composite")
    if composite is None:
        return "insufficient_evidence", "Topic was not scored — no interview evidence."

    if composite >= STRENGTH_MIN and coverage == "grilled":
        return "supported", "Interview answers supported the resume claim with substance."
    if composite < GAP_WEAK:
        return "unsupported", "Interview answers did not substantiate the resume claim."
    return "partial", "Interview partially supported the resume claim."


def _topic_notes(topics: list[ReportTopicInput]) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    for t in topics:
        rollup = t.rollup_scores or {}
        insuff = _insufficient(rollup)
        dims = rollup.get("dims")
        notes.append(
            {
                "topic_id": t.topic_id,
                "title": t.title,
                "kind": t.kind,
                "status": t.status,
                "coverage": _coverage(rollup),
                "composite": None if insuff else rollup.get("composite"),
                "dims": None if insuff else dims,
                "intents": [] if insuff else list(t.intents or []),
                "flags": {} if insuff else dict(rollup.get("flags") or {}),
                "n_turns": 0 if insuff else int(rollup.get("n_turns") or 0),
                "evidence_quotes": [] if insuff else _normalize_quotes(t.evidence_quotes),
                "insufficient_evidence": insuff,
            }
        )
    return notes


def _resume_linked_notes(
    topics: list[ReportTopicInput],
    claims: list[ReportClaimInput],
    turns: list[ReportTurnInput],
) -> list[dict[str, Any]]:
    by_id = {c.claim_id: c for c in claims if c.document_type == "resume"}
    notes: list[dict[str, Any]] = []
    for t in topics:
        if not t.claim_id or t.claim_id not in by_id:
            continue
        claim = by_id[t.claim_id]
        outcome, detail = _interview_outcome(t.rollup_scores or {})
        answer = _answer_for_topic(turns, t.topic_id)
        if answer and outcome in ("supported", "partial", "unsupported", "contradicted"):
            detail = _clip(f"{detail} Candidate said: {answer}", _MAX_DETAIL_CHARS)
        notes.append(
            {
                "claim_id": claim.claim_id,
                "claim_text": claim.text,
                "claim_type": claim.claim_type,
                "topic_id": t.topic_id,
                "topic_title": t.title,
                "interview_outcome": outcome,
                "detail": detail,
                "evidence_quotes": _normalize_quotes(t.evidence_quotes),
            }
        )
    return notes


def _jd_alignment(
    topics: list[ReportTopicInput], *, has_jd: bool
) -> dict[str, Any] | None:
    if not has_jd:
        return None
    covered: list[dict[str, Any]] = []
    weak: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for t in topics:
        if t.kind != "jd_must":
            continue
        rollup = t.rollup_scores or {}
        item = {
            "topic_id": t.topic_id,
            "title": t.title,
            "coverage": _coverage(rollup),
            "composite": rollup.get("composite"),
        }
        cov = item["coverage"]
        if cov == "grilled":
            covered.append(item)
        elif cov == "light":
            weak.append(item)
        else:
            missing.append(item)
    return {"covered": covered, "weak": weak, "missing": missing}


def _result_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for it in items:
        row = {
            "topic_id": str(it["topic_id"]),
            "title": it["title"],
            "kind": it["kind"],
            "score": it.get("score"),
            "reason": it["reason"],
        }
        if it.get("severity") is not None:
            row["severity"] = it["severity"]
        out.append(row)
    return out


def _appendix(
    turns: list[ReportTurnInput], corrections: list[ReportCorrectionInput]
) -> dict[str, Any]:
    key_quotes: list[dict[str, Any]] = []
    for t in turns:
        if t.role != "user" or not (t.text or "").strip():
            continue
        key_quotes.append(
            {
                "topic_id": t.topic_id,
                "role": "user",
                "text": _clip(t.text, _MAX_QUOTE_CHARS),
            }
        )
        if len(key_quotes) >= _MAX_APPENDIX_QUOTES:
            break
    highlights = [
        {
            "raw": c.raw,
            "normalized": c.normalized,
            "replacements": list(c.replacements),
        }
        for c in corrections[:_MAX_CORRECTIONS]
        if c.replacements
    ]
    return {"key_quotes": key_quotes, "correction_highlights": highlights}


def assemble_report(data: ReportAssemblyInput) -> dict[str, Any]:
    """Build a schema-valid report_json from scored session inputs. Prose left empty."""
    cov = data.coverage_summary or {}
    counts = dict(cov.get("counts") or {"grilled": 0, "light": 0, "skipped": 0})
    jd_must = dict(cov.get("jd_must") or {"grilled": 0, "light": 0, "skipped": 0})
    topics_cov = [
        {
            "topic_id": str(t["topic_id"]),
            "title": t["title"],
            "kind": t["kind"],
            "coverage": t["coverage"],
        }
        for t in cov.get("topics") or []
    ]
    planned_n = len(topics_cov) if topics_cov else len(data.topics)

    report = {
        "schema_version": SCHEMA_VERSION,
        "session_meta": {
            "session_id": data.meta.session_id,
            "duration_minutes": data.meta.duration_minutes,
            "difficulty": data.meta.difficulty,
            "seniority": data.meta.seniority,
            "resume_filename": data.meta.resume_filename,
            "jd_filename": data.meta.jd_filename,
            "wrap_reason": data.meta.wrap_reason,
        },
        "overall_signal": {
            "hire_signal": data.hire_signal,
            "overall_score": data.overall_score,
            "dims": dict(cov.get("dims") or {}),
            "summary": None,
        },
        "coverage_map": {
            "planned_n": planned_n,
            "counts": counts,
            "jd_must": jd_must,
            "topics": topics_cov,
        },
        "topic_notes": _topic_notes(data.topics),
        "strengths": _result_items(data.strengths),
        "gaps": _result_items(data.gaps),
        "resume_linked_notes": _resume_linked_notes(data.topics, data.claims, data.turns),
        "jd_alignment": _jd_alignment(data.topics, has_jd=bool(data.meta.jd_filename)),
        "appendix": _appendix(data.turns, data.corrections),
        "prose": {
            "summary": None,
            "pros": [],
            "cons": [],
            "next_steps": [],
        },
    }
    validate_report_json(report)
    return report
