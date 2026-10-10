"""Phase 6 — markdown render from report_json."""

from __future__ import annotations

from app.services.report_markdown import render_report_markdown


def _report() -> dict:
    return {
        "schema_version": "v1",
        "session_meta": {
            "session_id": "11111111-1111-1111-1111-111111111111",
            "duration_minutes": 15,
            "difficulty": "standard",
            "seniority": "mid",
            "resume_filename": "resume.pdf",
            "jd_filename": "jd.pdf",
            "wrap_reason": "timer",
        },
        "overall_signal": {
            "hire_signal": "solid",
            "overall_score": 3.5,
            "dims": {"depth": 3.2, "honesty": 4.0},
            "summary": "Solid practice signal with one major gap.",
        },
        "coverage_map": {
            "planned_n": 2,
            "counts": {"grilled": 1, "light": 0, "skipped": 1},
            "jd_must": {"grilled": 0, "light": 0, "skipped": 1},
            "topics": [],
        },
        "topic_notes": [
            {
                "topic_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "title": "Latency work",
                "kind": "claim",
                "status": "scored",
                "coverage": "grilled",
                "composite": 3.8,
                "dims": {"depth": 3.5},
                "intents": ["measurement"],
                "flags": {},
                "n_turns": 2,
                "evidence_quotes": [],
                "insufficient_evidence": False,
            },
            {
                "topic_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "title": "On-call",
                "kind": "jd_must",
                "status": "skipped",
                "coverage": "skipped",
                "composite": None,
                "dims": None,
                "intents": [],
                "flags": {},
                "n_turns": 0,
                "evidence_quotes": [],
                "insufficient_evidence": True,
            },
        ],
        "strengths": [
            {
                "topic_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "title": "Latency work",
                "kind": "claim",
                "score": 3.8,
                "reason": "strong depth",
            }
        ],
        "gaps": [
            {
                "topic_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "title": "On-call",
                "kind": "jd_must",
                "score": None,
                "reason": "not covered",
                "severity": "minor",
            }
        ],
        "resume_linked_notes": [
            {
                "claim_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "claim_text": "Reduced p99 40%",
                "claim_type": "metric",
                "topic_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "topic_title": "Latency work",
                "interview_outcome": "supported",
                "detail": "Candidate explained Grafana measurement.",
                "evidence_quotes": [],
            }
        ],
        "jd_alignment": {
            "covered": [],
            "weak": [],
            "missing": [
                {
                    "topic_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                    "title": "On-call",
                    "coverage": "skipped",
                    "composite": None,
                }
            ],
        },
        "appendix": {"key_quotes": [], "correction_highlights": []},
        "prose": {
            "summary": "Solid practice signal with one major gap.",
            "pros": ["Clear latency measurement story"],
            "cons": ["On-call not covered"],
            "next_steps": [
                "Write an on-call story with timeline",
                "Rehearse ownership language",
                "Add one failure-mode example",
            ],
        },
    }


def test_render_report_markdown_includes_core_sections() -> None:
    md = render_report_markdown(_report())
    assert md.startswith("# Interview debrief")
    assert "solid" in md.lower()
    assert "Latency work" in md
    assert "insufficient evidence" in md.lower()
    assert "Clear latency measurement story" in md
    assert "Write an on-call story" in md
    assert "JD alignment" in md
    assert "Reduced p99 40%" in md
