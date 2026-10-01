"""Rubric v2 scoring — pure helpers (PRD §6). No DB / LLM.

Per-turn dims (0–5): correctness, relevance, depth, structure, honesty.
0 missing → 3 meets bar for the selected seniority → 5 exceptional for that level.
v2: integrity/vague caps, weakest-turn topic weighting, collapse + recycled-story detection,
severity-ranked gaps, and gap-gated hire signal.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.services.grill_policy import looks_like_idk
from app.services.grill_prompt import RetrievedChunk

RUBRIC_VERSION = "v2"
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
# Impact claims with no concrete specifics ("felt faster") can't read as meeting the bar.
VAGUE_COMPOSITE_CAP = 2.25
# Any integrity flag (bluff/contradiction) on a topic caps the whole topic, not just that turn.
TOPIC_INTEGRITY_CAP = 2.5
# Topic composite = (1 - w) * mean + w * weakest substantive turn — a polished first answer
# can't hide a collapse under follow-up.
WEAKEST_TURN_WEIGHT = 0.4
STRONG_TURN = 3.5
WEAK_TURN = 2.5
STRENGTH_MIN = 3.5
GAP_WEAK = 2.5
# Each integrity-flagged topic scales the session overall by this factor.
INTEGRITY_PENALTY = 0.9
# Share of a topic's answer tokens already used by an earlier topic → same story recycled.
RECYCLE_OVERLAP = 0.6
RECYCLE_MIN_TOKENS = 15
SCORABLE_CONFIDENCE = 0.5
TURN_FLAGS = ("bluff", "contradiction", "idk", "vague")

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
_VAGUE = re.compile(
    r"\b(or something|i guess|maybe|kind of|you know|stuff|trial and error|"
    r"not (?:totally |really |entirely )?sure|(?:don'?t|do not) (?:really )?remember|"
    r"felt (?:faster|better|right|good)|looked (?:good|great|better)|"
    r"spoke for themselves|huge win)\b",
    re.I,
)
_VAGUE_MIN_HITS = 2


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


def composite(dims: dict[str, float], *, bluff: bool = False, vague: bool = False) -> float:
    total = sum(DIM_WEIGHTS[d] * float(dims.get(d, 0)) for d in DIMS)
    if vague:
        total = min(total, VAGUE_COMPOSITE_CAP)
    if bluff:
        total = min(total, BLUFF_COMPOSITE_CAP)
    return round(total, 2)


def _integrity(flags: dict[str, Any]) -> bool:
    return bool(flags.get("bluff") or flags.get("contradiction"))


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
    vague_hits = _VAGUE.findall(text)
    if len(vague_hits) >= _VAGUE_MIN_HITS:
        flags["vague"] = True
        depth = min(depth, 2)
        correctness = min(correctness, 2)
        honesty = min(honesty, 3)
        rationale_bits.append(f"{len(vague_hits)} hedges/unverifiable claims")

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
    flags: dict[str, Any] = {k: True for k in TURN_FLAGS if raw_flags.get(k) is True}
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
    if _integrity(draft.flags):
        return "probe"
    if draft.flags.get("vague") or (draft.depth <= 2 and draft.relevance >= 2):
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
    turn_composites = [
        composite(s.dims, bluff=_integrity(s.flags), vague=bool(s.flags.get("vague")))
        for s in scores
    ]
    mean = sum(w * c for w, c in zip(weights, turn_composites)) / wsum
    real = [c for s, c in zip(scores, turn_composites) if not s.flags.get("idk")]
    if len(real) >= 2:
        mean = (1 - WEAKEST_TURN_WEIGHT) * mean + WEAKEST_TURN_WEIGHT * min(real)
    if any(_integrity(s.flags) for s in scores):
        mean = min(mean, TOPIC_INTEGRITY_CAP)
    topic_composite = round(mean, 2)

    flags = {k: sum(1 for s in scores if s.flags.get(k)) for k in TURN_FLAGS}
    # Collapse: a weak answer after an earlier strong one on the same topic.
    flags["collapse"] = sum(
        1 for i, c in enumerate(real) if c < WEAK_TURN and any(p >= STRONG_TURN for p in real[:i])
    )
    substantive = len(real)
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


def hire_signal(
    overall: float | None,
    *,
    integrity_topics: int = 0,
    major_gaps: int = 0,
    minor_gaps: int = 0,
) -> str | None:
    """Score band, then gates: "strong" needs a clean sheet; repeated integrity or major gaps → mixed."""
    if overall is None:
        return None
    levels = ["needs_work", "mixed", "solid", "strong"]
    idx = 0 if overall < 2.25 else 1 if overall < 3.0 else 2 if overall < 4.0 else 3
    if integrity_topics or major_gaps or minor_gaps:
        idx = min(idx, 2)
    if integrity_topics >= 2 or major_gaps >= 2:
        idx = min(idx, 1)
    return levels[idx]


def recycled_topics(answers: list[tuple[str, str]]) -> set[str]:
    """Topics whose answers mostly reuse an earlier topic's story.

    `answers` is (topic_id, concatenated answer text) in the order topics were first answered.
    """
    seen: list[set[str]] = []
    out: set[str] = set()
    for topic_id, text in answers:
        toks = _tokens(text)
        if len(toks) < RECYCLE_MIN_TOKENS:
            continue
        if any(len(toks & prev) / min(len(toks), len(prev)) >= RECYCLE_OVERLAP for prev in seen):
            out.add(topic_id)
        seen.append(toks)
    return out


@dataclass(frozen=True)
class TopicRollupRow:
    topic_id: str
    title: str
    kind: str
    status: str
    rollup: dict[str, Any]
    recycled: bool = False


def _gap_for(t: TopicRollupRow) -> tuple[str, str] | None:
    """(severity, reason) for one non-warmup topic, most serious first; None if no gap."""
    r = t.rollup
    flags = r.get("flags", {})
    n_turns = r.get("n_turns") or 0
    real = n_turns - flags.get("idk", 0)
    comp = r.get("composite")
    if flags.get("bluff"):
        return "major", "answer contradicted or overstated the resume evidence"
    if flags.get("contradiction"):
        return "major", "inconsistent with earlier answers"
    if flags.get("collapse"):
        return "major", "collapsed under follow-up — could not back up the earlier answer"
    if real and flags.get("vague", 0) * 2 >= real:
        return "major", "vague — impact claims without concrete specifics"
    if r.get("coverage") == "skipped" and n_turns:
        return "major", "dead end — candidate did not know"
    if comp is not None and comp < GAP_WEAK:
        return "major", f"weak {min(r['dims'], key=r['dims'].get)}"
    if t.recycled:
        return "minor", "reused the same example as another topic"
    if t.kind == "jd_must" and not n_turns:
        return "minor", "not covered"
    if t.kind == "jd_must" and r.get("coverage") == "light":
        return "minor", "only lightly covered — no follow-up"
    return None


def _is_strength(t: TopicRollupRow) -> bool:
    r = t.rollup
    flags = r.get("flags", {})
    return (
        r.get("coverage") == "grilled"
        and not t.recycled
        and r["composite"] >= STRENGTH_MIN
        and r.get("dims", {}).get("honesty", 0) >= 3
        and not any(flags.get(k) for k in ("bluff", "contradiction", "collapse", "vague"))
    )


def rollup_session(topics: list[TopicRollupRow]) -> dict[str, Any]:
    """Weighted session rollup → overall, hire_signal, strengths, gaps, coverage summary."""
    scored = [t for t in topics if t.rollup.get("composite") is not None]
    wsum = sum(KIND_WEIGHTS.get(t.kind, 1.0) for t in scored)
    integrity_topics = sum(1 for t in scored if _integrity(t.rollup.get("flags", {})))
    overall = (
        round(
            sum(KIND_WEIGHTS.get(t.kind, 1.0) * t.rollup["composite"] for t in scored)
            / wsum
            * INTEGRITY_PENALTY**integrity_topics,
            2,
        )
        if scored and wsum > 0
        else None
    )
    dims: dict[str, float] = {}
    if scored and wsum > 0:
        for d in DIMS:
            dims[d] = round(
                sum(KIND_WEIGHTS.get(t.kind, 1.0) * t.rollup["dims"][d] for t in scored) / wsum, 2
            )

    def _item(t: TopicRollupRow, reason: str, **extra: Any) -> dict[str, Any]:
        return {
            "topic_id": t.topic_id,
            "title": t.title,
            "kind": t.kind,
            "score": t.rollup.get("composite"),
            "reason": reason,
            **extra,
        }

    core = [t for t in scored if t.kind != "warmup"]
    strengths = [
        _item(t, f"strong {max(t.rollup['dims'], key=t.rollup['dims'].get)}")
        for t in sorted(core, key=lambda t: -t.rollup["composite"])
        if _is_strength(t)
    ][:3]

    gaps: list[dict[str, Any]] = []
    for t in topics:
        if t.kind == "warmup":
            continue
        gap = _gap_for(t)
        if gap:
            gaps.append(_item(t, gap[1], severity=gap[0]))
    major = sum(1 for g in gaps if g["severity"] == "major")

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
        "hire_signal": hire_signal(
            overall,
            integrity_topics=integrity_topics,
            major_gaps=major,
            minor_gaps=len(gaps) - major,
        ),
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
