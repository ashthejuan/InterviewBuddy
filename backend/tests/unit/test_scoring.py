"""Rubric v1 — heuristic scorer, LLM output validation, signals, rollups."""

from __future__ import annotations

import json
import uuid

import pytest

from app.services.grill_prompt import RetrievedChunk
from app.services.scoring import (
    ScoredTurn,
    TopicRollupRow,
    TurnScoreDraft,
    composite,
    heuristic_score,
    hire_signal,
    parse_score_json,
    rollup_session,
    rollup_topic,
    score_signal,
)

RESUME_ID = uuid.uuid4()
CHUNK = RetrievedChunk(
    id=uuid.uuid4(),
    content="Reduced p99 latency 40% via Redis caching on the billing API",
    document_id=RESUME_ID,
)
QUESTION = "You mentioned reducing p99 latency 40%. How did you measure it?"


def _draft(**kw) -> TurnScoreDraft:
    base = {
        "correctness": 3, "relevance": 3, "depth": 3, "structure": 3, "honesty": 4,
        "confidence": 0.7, "rationale": "", "flags": {},
    }
    base.update(kw)
    return TurnScoreDraft(**base)


def test_idk_scores_honest_gap_not_zero() -> None:
    d = heuristic_score(question=QUESTION, answer="Honestly, I don't know.", evidence=[CHUNK])
    assert d.flags == {"idk": True}
    assert d.honesty == 5 and d.depth == 0
    assert composite(d.dims()) > 0


def test_detailed_answer_scores_higher_than_short_one() -> None:
    short = heuristic_score(question=QUESTION, answer="I used caching.", evidence=[CHUNK])
    long = heuristic_score(
        question=QUESTION,
        answer=(
            "I profiled the billing API first because p99 latency spiked at peak. "
            "Then I added Redis caching for the pricing lookups, which meant 40% lower p99 "
            "latency measured in Grafana over two weeks. The tradeoff was cache invalidation, "
            "so I keyed entries on plan version."
        ),
        evidence=[CHUNK],
    )
    assert long.depth > short.depth
    assert long.relevance > short.relevance
    assert long.structure > short.structure
    assert not long.flags
    assert long.evidence and long.evidence[0].chunk_id == CHUNK.id


def test_unsupported_metric_is_flagged_as_bluff() -> None:
    d = heuristic_score(
        question=QUESTION,
        answer="I cut p99 latency by 90% with caching on the billing API in a week.",
        evidence=[CHUNK],
        doc_sources={RESUME_ID: "resume"},
    )
    assert d.flags["bluff"] is True
    assert d.flags["unsupported_metrics"] == ["90%"]
    assert d.honesty == 2
    assert d.evidence[0].source == "resume"


def test_matching_metric_is_not_a_bluff() -> None:
    d = heuristic_score(
        question=QUESTION,
        answer="I cut p99 latency by 40 percent with caching on the billing API.",
        evidence=[CHUNK],
    )
    assert "bluff" not in d.flags


def test_seniority_raises_the_bar() -> None:
    answer = "I added caching on the billing API to reduce the p99 latency for checkout."
    junior = heuristic_score(question=QUESTION, answer=answer, evidence=[CHUNK], seniority="junior")
    staff = heuristic_score(question=QUESTION, answer=answer, evidence=[CHUNK], seniority="staff")
    assert junior.depth > staff.depth


def test_parse_score_json_clamps_and_rejects_invented_quotes() -> None:
    raw = json.dumps(
        {
            "correctness": 9, "relevance": -2, "depth": "4", "structure": 3.4, "honesty": 5,
            "confidence": 3, "rationale": "ok",
            "flags": {"bluff": True, "contradiction": "yes"},
            "evidence": [
                {"index": 0, "quote": "Totally made up text"},
                {"index": 7, "quote": "out of range"},
            ],
        }
    )
    d = parse_score_json(raw, answer="some answer", evidence=[CHUNK])
    assert d.dims() == {"correctness": 5, "relevance": 0, "depth": 4, "structure": 3, "honesty": 5}
    assert d.confidence == 1.0
    assert d.flags == {"bluff": True}
    assert len(d.evidence) == 1
    assert d.evidence[0].quote == CHUNK.content


def test_parse_score_json_keeps_verified_quote_and_detects_idk() -> None:
    raw = "```json\n" + json.dumps(
        {
            "correctness": 1, "relevance": 2, "depth": 0, "structure": 2, "honesty": 5,
            "evidence": [{"index": 0, "quote": "p99 latency 40%"}],
        }
    ) + "\n```"
    d = parse_score_json(raw, answer="I don't know", evidence=[CHUNK])
    assert d.evidence[0].quote == "p99 latency 40%"
    assert d.flags["idk"] is True


def test_parse_score_json_missing_dims_raises() -> None:
    with pytest.raises(ValueError):
        parse_score_json('{"correctness": 3}', answer="x", evidence=[])


def test_score_signal_mapping() -> None:
    assert score_signal(_draft(flags={"bluff": True}), kind="claim") == "probe"
    assert score_signal(_draft(flags={"contradiction": True}), kind="jd_must") == "probe"
    assert score_signal(_draft(depth=1, relevance=3), kind="claim") == "deepen"
    assert score_signal(_draft(), kind="claim") == "scorable"
    assert score_signal(_draft(confidence=0.2), kind="claim") is None
    assert score_signal(_draft(flags={"idk": True}), kind="claim") is None
    assert score_signal(_draft(flags={"bluff": True}), kind="warmup") is None


def test_bluffed_turn_never_outscores_idk() -> None:
    idk = composite({"correctness": 1, "relevance": 2, "depth": 0, "structure": 2, "honesty": 5})
    bluff = composite(
        {"correctness": 4, "relevance": 4, "depth": 4, "structure": 4, "honesty": 2}, bluff=True
    )
    assert bluff < idk


def _st(v: int, conf: float = 0.7, **flags) -> ScoredTurn:
    return ScoredTurn(
        dims={d: v for d in ("correctness", "relevance", "depth", "structure", "honesty")},
        confidence=conf,
        flags=flags,
    )


def test_rollup_topic_coverage_labels() -> None:
    assert rollup_topic([], status="skipped")["coverage"] == "skipped"
    assert rollup_topic([_st(3)], status="scored")["coverage"] == "light"
    grilled = rollup_topic([_st(3), _st(4)], status="scored")
    assert grilled["coverage"] == "grilled"
    assert grilled["composite"] == pytest.approx(3.5, abs=0.01)
    assert rollup_topic([_st(1, idk=True)], status="skipped")["coverage"] == "skipped"


def test_rollup_session_weights_warmup_lightly() -> None:
    rows = [
        TopicRollupRow("w", "Warmup", "warmup", "scored", rollup_topic([_st(0)], status="scored")),
        TopicRollupRow("c", "Latency", "claim", "scored", rollup_topic([_st(4), _st(4)], status="scored")),
    ]
    out = rollup_session(rows)
    # (0.25*0 + 1.0*4) / 1.25 = 3.2
    assert out["overall_score"] == pytest.approx(3.2, abs=0.01)
    assert out["hire_signal"] == "solid"
    assert out["strengths"][0]["topic_id"] == "c"
    assert out["coverage_summary"]["counts"] == {"grilled": 1, "light": 1, "skipped": 0}


def test_rollup_session_gaps_and_no_scores() -> None:
    rows = [
        TopicRollupRow("b", "Bluffed", "claim", "scored",
                       rollup_topic([_st(4, bluff=True)], status="scored")),
        TopicRollupRow("i", "IDK", "jd_must", "skipped",
                       rollup_topic([_st(1, idk=True)], status="skipped")),
        TopicRollupRow("u", "Unasked", "claim", "skipped", rollup_topic([], status="skipped")),
    ]
    out = rollup_session(rows)
    reasons = {g["topic_id"]: g["reason"] for g in out["gaps"]}
    assert "overstated" in reasons["b"]
    assert "did not know" in reasons["i"]
    assert "u" not in reasons
    assert out["coverage_summary"]["jd_must"]["skipped"] == 1
    assert rollup_session([])["hire_signal"] is None


def test_hire_signal_bands_and_bluff_downgrade() -> None:
    assert hire_signal(1.0) == "needs_work"
    assert hire_signal(2.5) == "mixed"
    assert hire_signal(3.4) == "solid"
    assert hire_signal(4.2) == "strong"
    assert hire_signal(4.2, bluff_topics=2) == "solid"
