"""Rubric v1 scoring — pure helpers (PRD §6). No DB / LLM.

Per-turn dims (0–5): correctness, relevance, depth, structure, honesty.
0 missing → 3 meets bar for the selected seniority → 5 exceptional for that level.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.services.grill_policy import looks_like_idk
from app.services.grill_prompt import RetrievedChunk

RUBRIC_VERSION = "v1"
DIMS = ("correctness", "relevance", "depth", "structure", "honesty")
DIM_WEIGHTS = {
    "correctness": 0.25,
    "relevance": 0.15,
    "depth": 0.25,
    "structure": 0.15,
    "honesty": 0.20,
}
# Core grill > behavioral > warmup (PRD §6 session output)
KIND_WEIGHTS = {"warmup": 0.25, "behavioral": 0.75}
# Bluffing is penalized more than an honest gap: a bluffed turn never out-scores "I don't know".
BLUFF_COMPOSITE_CAP = 1.5
SCORABLE_CONFIDENCE = 0.5

_SENIORITY_OFFSET = {"intern": 1, "junior": 1, "mid": 0, "senior": -1, "staff": -1}
_STOP = frozenset(
    "a an the and or but if of to in on at for with by from as is are was were be been "
    "it its this that these those i we you they he she my our your their me us them "
    "what how why when where which who did do does done have has had can could would "
    "should will about into over than then so very just also really there here".split()
)
_TOKEN = re.compile(r"[a-z][a-z0-9+#.\-]*[a-z0-9+#]|[a-z]")
_CLAIMED_RATIO = re.compile(r"(\d+(?:\.\d+)?)\s*(%|percent\b|x\b)", re.I)
_OWNERSHIP = re.compile(
    r"\b(i\s+(?:built|designed|owned|led|wrote|shipped|drove|migrated|implemented|debugged|"
    r"profiled|measured|reduced|improved|chose|decided))\b",
    re.I,
)
_CONNECTORS = re.compile(
    r"\b(because|so that|therefore|first|then|finally|as a result|the result|tradeoff|"
    r"trade-off|which meant|instead|however)\b",
    re.I,
)


@dataclass(frozen=True)
class EvidenceRef:
    chunk_id: uuid.UUID
    quote: str
    source: str | None = None


@dataclass
class TurnScoreDraft:
    correctness: int
    relevance: int
    depth: int
    structure: int
    honesty: int
    confidence: float
    rationale: str
    flags: dict[str, Any] = field(default_factory=dict)
    evidence: list[EvidenceRef] = field(default_factory=list)

    def dims(self) -> dict[str, int]:
        return {d: getattr(self, d) for d in DIMS}


def _clamp(v: Any, lo: int = 0, hi: int = 5) -> int:
    try:
        n = round(float(v))
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, n))


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall((text or "").lower()) if t not in _STOP and len(t) > 1}


def _ratios(text: str) -> set[str]:
    return {f"{float(n):g}{'x' if u.lower() == 'x' else '%'}" for n, u in _CLAIMED_RATIO.findall(text)}


def composite(dims: dict[str, float], *, bluff: bool = False) -> float:
    total = sum(DIM_WEIGHTS[d] * float(dims.get(d, 0)) for d in DIMS)
    if bluff:
        total = min(total, BLUFF_COMPOSITE_CAP)
    return round(total, 2)


def _source_for(chunk: RetrievedChunk, doc_sources: dict[uuid.UUID, str]) -> str | None:
    return doc_sources.get(chunk.document_id) if chunk.document_id else None


def heuristic_score(
    *,
    question: str,
    answer: str,
    evidence: list[RetrievedChunk],
    seniority: str = "mid",
    doc_sources: dict[uuid.UUID, str] | None = None,
) -> TurnScoreDraft:
    """Deterministic fallback scorer — coarse, low confidence, never awards 5 on correctness."""
    doc_sources = doc_sources or {}
    text = (answer or "").strip()
    if looks_like_idk(text) and len(text.split()) < 25:
        top = [EvidenceRef(c.id, c.content.strip()[:300], _source_for(c, doc_sources)) for c in evidence[:1]]
        return TurnScoreDraft(
            correctness=1, relevance=2, depth=0, structure=2, honesty=5,
            confidence=0.6,
            rationale="Candidate said they don't know — an honest gap, nothing substantive to score.",
            flags={"idk": True},
            evidence=top,
        )

    words = text.split()
    n = len(words)
    depth = 1 if n < 8 else 2 if n < 25 else 3 if n < 60 else 4 if n < 120 else 5
    specific = bool(_CLAIMED_RATIO.search(text) or re.search(r"\d", text) or _OWNERSHIP.search(text))
    if specific and n >= 8:
        depth += 1

    answer_tokens = _tokens(text)
    context_tokens = _tokens(question)
    for c in evidence:
        context_tokens |= _tokens(c.content)
    hits = len(answer_tokens & context_tokens)
    relevance = 1 if hits == 0 else 2 if hits < 2 else 3 if hits < 4 else 4 if hits < 7 else 5

    sentences = [s for s in re.split(r"[.!?]+", text) if len(s.split()) >= 3]
    structure = 1 + min(len(sentences), 2) + min(len(_CONNECTORS.findall(text)), 2)

    offset = _SENIORITY_OFFSET.get(seniority, 0)
    depth = _clamp(depth + offset)
    correctness = _clamp(round((relevance + depth) / 2) + offset, 1, 4)

    flags: dict[str, Any] = {}
    honesty = 4
    rationale_bits = [f"{n} words, {hits} terms overlapping the question/evidence"]
    # Bluff check: a claimed %/multiplier the resume never states, when the resume does state one.
    evidence_text = " ".join(c.content for c in evidence)
    claimed = _ratios(text)
    stated = _ratios(evidence_text)
    unsupported = sorted(claimed - stated)
    if unsupported and stated:
        flags["bluff"] = True
        flags["unsupported_metrics"] = unsupported
        honesty = 2
        rationale_bits.append(
            f"claims {', '.join(unsupported)} but the resume states {', '.join(sorted(stated))}"
        )

    matched = [c for c in evidence if len(_tokens(c.content) & answer_tokens) >= 2][:3]
    if not matched:
        matched = evidence[:1]
    refs = [EvidenceRef(c.id, c.content.strip()[:300], _source_for(c, doc_sources)) for c in matched]

    return TurnScoreDraft(
        correctness=correctness,
        relevance=relevance,
        depth=depth,
        structure=_clamp(structure),
        honesty=honesty,
        confidence=0.5,
        rationale="Heuristic: " + "; ".join(rationale_bits) + ".",
        flags=flags,
        evidence=refs,
    )


def parse_score_json(
    raw: str,
    *,
    answer: str,
    evidence: list[RetrievedChunk],
    doc_sources: dict[uuid.UUID, str] | None = None,
) -> TurnScoreDraft:
    """Validate scorer LLM output. Raises ValueError on unusable output.

    Evidence quotes must come from the retrieved chunks — an unverifiable quote is replaced by
    the chunk text itself so `turn_evidence` never holds model-invented text.
    """
    doc_sources = doc_sources or {}
    text = raw.strip()
    fence = re.search(r"\{.*\}", text, re.S)
    if fence is None:
        raise ValueError("no JSON object in scorer output")
    data = json.loads(fence.group(0))
    if not isinstance(data, dict) or not all(d in data for d in DIMS):
        raise ValueError("scorer output missing rubric dims")

    raw_flags = data.get("flags") if isinstance(data.get("flags"), dict) else {}
    flags: dict[str, Any] = {k: True for k in ("bluff", "contradiction", "idk") if raw_flags.get(k) is True}
    if looks_like_idk(answer) and len(answer.split()) < 25:
        flags["idk"] = True

    refs: list[EvidenceRef] = []
    seen: set[uuid.UUID] = set()
    for item in data.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index", -1))
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx >= len(evidence) or evidence[idx].id in seen:
            continue
        chunk = evidence[idx]
        quote = str(item.get("quote") or "").strip()
        if not quote or quote.lower() not in chunk.content.lower():
            quote = chunk.content.strip()
        refs.append(EvidenceRef(chunk.id, quote[:300], _source_for(chunk, doc_sources)))
        seen.add(chunk.id)
        if len(refs) >= 3:
            break

    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5

    return TurnScoreDraft(
        correctness=_clamp(data["correctness"]),
        relevance=_clamp(data["relevance"]),
        depth=_clamp(data["depth"]),
        structure=_clamp(data["structure"]),
        honesty=_clamp(data["honesty"]),
        confidence=confidence,
        rationale=str(data.get("rationale") or "").strip()[:600],
        flags=flags,
        evidence=refs,
    )


def score_signal(draft: TurnScoreDraft, *, kind: str) -> str | None:
    """Rubric → frontier hint (PRD §6 "Grill ↔ scores"): probe | deepen | scorable | None."""
    if kind == "warmup" or draft.flags.get("idk"):
        return None
    if draft.flags.get("bluff") or draft.flags.get("contradiction"):
        return "probe"
    if draft.depth <= 2 and draft.relevance >= 2:
        return "deepen"
    if (
        min(draft.correctness, draft.relevance, draft.depth) >= 3
        and draft.confidence >= SCORABLE_CONFIDENCE
    ):
        return "scorable"
    return None


@dataclass(frozen=True)
class ScoredTurn:
    dims: dict[str, int]
    confidence: float | None
    flags: dict[str, Any]


def rollup_topic(scores: list[ScoredTurn], *, status: str) -> dict[str, Any]:
    """Confidence-weighted dim means + composite + coverage label for one topic."""
    if not scores:
        return {"n_turns": 0, "coverage": "skipped", "composite": None, "dims": {}, "flags": {}}
    weights = [max(0.1, s.confidence if s.confidence is not None else 0.5) for s in scores]
    wsum = sum(weights)
    dims = {
        d: round(sum(w * s.dims[d] for w, s in zip(weights, scores)) / wsum, 2) for d in DIMS
    }
    turn_composites = [composite(s.dims, bluff=bool(s.flags.get("bluff"))) for s in scores]
    topic_composite = round(sum(w * c for w, c in zip(weights, turn_composites)) / wsum, 2)
    flags = {
        k: sum(1 for s in scores if s.flags.get(k))
        for k in ("bluff", "contradiction", "idk")
    }
    substantive = sum(1 for s in scores if not s.flags.get("idk"))
    if status == "skipped" or substantive == 0:
        coverage = "skipped"
    elif substantive >= 2:
        coverage = "grilled"
    else:
        coverage = "light"
    return {
        "rubric_version": RUBRIC_VERSION,
        "n_turns": len(scores),
        "coverage": coverage,
        "composite": topic_composite,
        "dims": dims,
        "flags": {k: v for k, v in flags.items() if v},
    }


def hire_signal(overall: float | None, *, bluff_topics: int = 0) -> str | None:
    if overall is None:
        return None
    levels = ["needs_work", "mixed", "solid", "strong"]
    idx = 0 if overall < 2.25 else 1 if overall < 3.0 else 2 if overall < 3.8 else 3
    # Consistency check: repeated bluffing across topics caps the signal one level lower.
    if bluff_topics >= 2 and idx >= 2:
        idx -= 1
    return levels[idx]


@dataclass(frozen=True)
class TopicRollupRow:
    topic_id: str
    title: str
    kind: str
    status: str
    rollup: dict[str, Any]


def rollup_session(topics: list[TopicRollupRow]) -> dict[str, Any]:
    """Weighted session rollup → overall, hire_signal, strengths, gaps, coverage summary."""
    scored = [t for t in topics if t.rollup.get("composite") is not None]
    wsum = sum(KIND_WEIGHTS.get(t.kind, 1.0) for t in scored)
    overall = (
        round(sum(KIND_WEIGHTS.get(t.kind, 1.0) * t.rollup["composite"] for t in scored) / wsum, 2)
        if scored and wsum > 0
        else None
    )
    dims: dict[str, float] = {}
    if scored and wsum > 0:
        for d in DIMS:
            dims[d] = round(
                sum(KIND_WEIGHTS.get(t.kind, 1.0) * t.rollup["dims"][d] for t in scored) / wsum, 2
            )
    bluff_topics = sum(1 for t in scored if t.rollup.get("flags", {}).get("bluff"))

    def _item(t: TopicRollupRow, reason: str) -> dict[str, Any]:
        return {
            "topic_id": t.topic_id,
            "title": t.title,
            "kind": t.kind,
            "score": t.rollup.get("composite"),
            "reason": reason,
        }

    core = [t for t in scored if t.kind != "warmup"]
    strengths = [
        _item(t, f"strong {max(t.rollup['dims'], key=t.rollup['dims'].get)}")
        for t in sorted(core, key=lambda t: -t.rollup["composite"])
        if t.rollup["composite"] >= 3.5 and not t.rollup.get("flags", {}).get("bluff")
    ][:3]

    gaps: list[dict[str, Any]] = []
    for t in topics:
        if t.kind == "warmup":
            continue
        flags = t.rollup.get("flags", {})
        if flags.get("bluff"):
            gaps.append(_item(t, "answer contradicted or overstated the resume evidence"))
        elif flags.get("contradiction"):
            gaps.append(_item(t, "inconsistent with earlier answers"))
        elif t.rollup.get("coverage") == "skipped" and t.rollup.get("n_turns"):
            gaps.append(_item(t, "dead end — candidate did not know"))
        elif t.rollup.get("composite") is not None and t.rollup["composite"] < 2.5:
            weakest = min(t.rollup["dims"], key=t.rollup["dims"].get)
            gaps.append(_item(t, f"weak {weakest}"))

    counts = {"grilled": 0, "light": 0, "skipped": 0}
    jd_must = {"grilled": 0, "light": 0, "skipped": 0}
    topic_cov: list[dict[str, Any]] = []
    for t in topics:
        cov = t.rollup.get("coverage") or "skipped"
        counts[cov] += 1
        if t.kind == "jd_must":
            jd_must[cov] += 1
        topic_cov.append({"topic_id": t.topic_id, "title": t.title, "kind": t.kind, "coverage": cov})

    return {
        "overall_score": overall,
        "hire_signal": hire_signal(overall, bluff_topics=bluff_topics),
        "strengths": strengths,
        "gaps": gaps,
        "coverage_summary": {
            "rubric_version": RUBRIC_VERSION,
            "counts": counts,
            "jd_must": jd_must,
            "dims": dims,
            "topics": topic_cov,
        },
    }
