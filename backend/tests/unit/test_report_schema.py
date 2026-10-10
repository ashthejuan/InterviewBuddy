"""Phase 6 — locked report_json contract (PRD §3A)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.services.report_schema import ReportJson, validate_report_json


def _minimal_report(**overrides) -> dict:
    base = {
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
            "dims": {
                "correctness": 3.5,
                "relevance": 3.4,
                "depth": 3.2,
                "structure": 3.6,
                "honesty": 4.0,
            },
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
                "evidence_quotes": [
                    {
                        "chunk_id": "33333333-3333-3333-3333-333333333333",
                        "quote": "Reduced p99 latency 40%",
                        "source": "resume",
                    }
                ],
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
        "gaps": [],
        "resume_linked_notes": [
            {
                "claim_id": "44444444-4444-4444-4444-444444444444",
                "claim_text": "Reduced p99 latency 40% via Redis",
                "claim_type": "metric",
                "topic_id": "22222222-2222-2222-2222-222222222222",
                "topic_title": "Latency work",
                "interview_outcome": "supported",
                "detail": "Candidate explained measurement via Grafana.",
                "evidence_quotes": [
                    {
                        "chunk_id": "33333333-3333-3333-3333-333333333333",
                        "quote": "Reduced p99 latency 40%",
                        "source": "resume",
                    }
                ],
            }
        ],
        "jd_alignment": None,
        "appendix": {
            "key_quotes": [
                {
                    "topic_id": "22222222-2222-2222-2222-222222222222",
                    "role": "user",
                    "text": "I measured p99 in Grafana over two weeks.",
                }
            ],
            "correction_highlights": [],
        },
        "prose": {
            "summary": None,
            "pros": [],
            "cons": [],
            "next_steps": [],
        },
    }
    base.update(overrides)
    return base


def test_validate_report_json_accepts_minimal_v1() -> None:
    report = validate_report_json(_minimal_report())
    assert isinstance(report, ReportJson)
    assert report.schema_version == "v1"
    assert report.overall_signal.hire_signal == "solid"
    assert report.prose.summary is None
    assert report.topic_notes[0].insufficient_evidence is False


def test_validate_report_json_rejects_unknown_schema_version() -> None:
    with pytest.raises(ValidationError):
        validate_report_json(_minimal_report(schema_version="v99"))


def test_validate_report_json_rejects_invented_hire_signal() -> None:
    raw = _minimal_report()
    raw["overall_signal"]["hire_signal"] = "amazing"
    with pytest.raises(ValidationError):
        validate_report_json(raw)


def test_validate_report_json_rejects_missing_topic_notes() -> None:
    raw = _minimal_report()
    del raw["topic_notes"]
    with pytest.raises(ValidationError):
        validate_report_json(raw)


def test_validate_report_json_allows_insufficient_evidence_topic() -> None:
    raw = _minimal_report()
    raw["topic_notes"] = [
        {
            "topic_id": "22222222-2222-2222-2222-222222222222",
            "title": "Skipped claim",
            "kind": "claim",
            "status": "skipped",
            "coverage": "skipped",
            "composite": None,
            "dims": None,
            "intents": [],
            "flags": {},
            "n_turns": 0,
            "evidence_quotes": [],
            "insufficient_evidence": True,
        }
    ]
    report = validate_report_json(raw)
    assert report.topic_notes[0].insufficient_evidence is True
    assert report.topic_notes[0].composite is None


def test_validate_report_json_prose_slots_are_optional_lists() -> None:
    raw = _minimal_report()
    raw["prose"] = {
        "summary": "Solid depth on latency.",
        "pros": ["Clear measurement story"],
        "cons": ["Thin on tradeoffs"],
        "next_steps": ["Practice explaining cache invalidation"],
    }
    report = validate_report_json(raw)
    assert report.prose.summary.startswith("Solid")
    assert len(report.prose.next_steps) == 1
