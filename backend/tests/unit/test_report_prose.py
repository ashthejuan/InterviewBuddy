"""Phase 6 — LLM/heuristic prose fill + grounding validation."""

from __future__ import annotations

import json

import pytest

from app.services.report_prose import (
    apply_prose,
    heuristic_prose,
    parse_prose_json,
)
from app.services.report_schema import validate_report_json


def _assembled() -> dict:
    return {
        "schema_version": "v1",
        "session_meta": {
            "session_id": "11111111-1111-1111-1111-111111111111",
            "duration_minutes": 15,
            "difficulty": "standard",
            "seniority": "mid",
            "resume_filename": "resume.pdf",
            "jd_filename": None,
            "wrap_reason": "user_ended",
        },
        "overall_signal": {
            "hire_signal": "solid",
            "overall_score": 3.5,
            "dims": {"correctness": 3.5, "relevance": 3.4, "depth": 3.2, "structure": 3.6, "honesty": 4.0},
            "summary": None,
        },
        "coverage_map": {
            "planned_n": 1,
            "counts": {"grilled": 1, "light": 0, "skipped": 0},
            "jd_must": {"grilled": 0, "light": 0, "skipped": 0},
            "topics": [
                {
                    "topic_id": "22222222-2222-2222-2222-222222222222",
                    "title": "Latency work",
                    "kind": "claim",
                    "coverage": "grilled",
                }
            ],
        },
        "topic_notes": [
            {
                "topic_id": "22222222-2222-2222-2222-222222222222",
                "title": "Latency work",
                "kind": "claim",
                "status": "scored",
                "coverage": "grilled",
                "composite": 3.8,
                "dims": {
                    "correctness": 4,
                    "relevance": 4,
                    "depth": 3,
                    "structure": 4,
                    "honesty": 4,
                },
                "intents": ["how latency was measured"],
                "flags": {},
                "n_turns": 2,
                "evidence_quotes": [],
                "insufficient_evidence": False,
            }
        ],
        "strengths": [
            {
                "topic_id": "22222222-2222-2222-2222-222222222222",
                "title": "Latency work",
                "kind": "claim",
                "score": 3.8,
                "reason": "strong depth",
            }
        ],
        "gaps": [
            {
                "topic_id": "33333333-3333-3333-3333-333333333333",
                "title": "Kafka ownership",
                "kind": "jd_must",
                "score": 1.5,
                "reason": "weak depth",
                "severity": "major",
            }
        ],
        "resume_linked_notes": [],
        "jd_alignment": None,
        "appendix": {"key_quotes": [], "correction_highlights": []},
        "prose": {"summary": None, "pros": [], "cons": [], "next_steps": []},
    }


def test_parse_prose_json_accepts_grounded_output() -> None:
    raw = json.dumps(
        {
            "summary": "Solid signal with clear latency storytelling.",
            "pros": ["Strong on Latency work"],
            "cons": ["Weak depth on Kafka ownership"],
            "next_steps": [
                "Rehearse Kafka ownership with a concrete incident",
                "Quantify tradeoffs in Latency work",
                "Practice admitting gaps early",
            ],
        }
    )
    prose = parse_prose_json(raw, assembled=_assembled())
    assert prose.summary.startswith("Solid")
    assert len(prose.next_steps) == 3


def test_parse_prose_json_rejects_unknown_topic_uuid() -> None:
    raw = json.dumps(
        {
            "summary": "ok",
            "pros": ["good"],
            "cons": ["bad about 99999999-9999-9999-9999-999999999999"],
            "next_steps": ["practice one", "practice two", "practice three"],
        }
    )
    with pytest.raises(ValueError, match="ungrounded"):
        parse_prose_json(raw, assembled=_assembled())


def test_parse_prose_json_rejects_wrong_shape() -> None:
    with pytest.raises(ValueError):
        parse_prose_json('{"summary": "only"}', assembled=_assembled())


def test_heuristic_prose_fills_from_strengths_and_gaps() -> None:
    prose = heuristic_prose(_assembled())
    assert prose.summary
    assert any("Latency" in p for p in prose.pros)
    assert any("Kafka" in c for c in prose.cons)
    assert 3 <= len(prose.next_steps) <= 5


def test_apply_prose_merges_and_validates() -> None:
    report = apply_prose(_assembled(), heuristic_prose(_assembled()))
    validated = validate_report_json(report)
    assert validated.prose.summary
    assert validated.overall_signal.summary == validated.prose.summary
