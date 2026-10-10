"""Phase 6 — deterministic report assembly (no LLM)."""

from __future__ import annotations

from app.services.report import (
    ReportAssemblyInput,
    ReportClaimInput,
    ReportCorrectionInput,
    ReportSessionMeta,
    ReportTopicInput,
    ReportTurnInput,
    assemble_report,
)
from app.services.report_schema import validate_report_json

TOPIC_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TOPIC_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
TOPIC_C = "cccccccc-cccc-cccc-cccc-cccccccccccc"
CLAIM_A = "dddddddd-dddd-dddd-dddd-dddddddddddd"
CLAIM_JD = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
CHUNK_A = "ffffffff-ffff-ffff-ffff-ffffffffffff"
SESSION = "11111111-1111-1111-1111-111111111111"


def _base_input(**kw) -> ReportAssemblyInput:
    topics = kw.pop(
        "topics",
        [
            ReportTopicInput(
                topic_id=TOPIC_A,
                title="Latency work",
                kind="claim",
                status="scored",
                claim_id=CLAIM_A,
                rollup_scores={
                    "coverage": "grilled",
                    "composite": 3.8,
                    "dims": {
                        "correctness": 4.0,
                        "relevance": 4.0,
                        "depth": 3.5,
                        "structure": 4.0,
                        "honesty": 4.0,
                    },
                    "flags": {},
                    "n_turns": 2,
                },
                intents=["how latency was measured"],
                evidence_quotes=[
                    {
                        "chunk_id": CHUNK_A,
                        "quote": "Reduced p99 latency 40%",
                        "source": "resume",
                    }
                ],
            ),
            ReportTopicInput(
                topic_id=TOPIC_B,
                title="Ownership of billing API",
                kind="claim",
                status="skipped",
                claim_id=None,
                rollup_scores={"coverage": "skipped", "composite": None, "flags": {}, "n_turns": 0},
                intents=[],
                evidence_quotes=[],
            ),
        ],
    )
    jd_filename = kw.pop("jd_filename", None)
    strengths = kw.pop(
        "strengths",
        [
            {
                "topic_id": TOPIC_A,
                "title": "Latency work",
                "kind": "claim",
                "score": 3.8,
                "reason": "strong depth",
            }
        ],
    )
    gaps = kw.pop(
        "gaps",
        [
            {
                "topic_id": TOPIC_B,
                "title": "Ownership of billing API",
                "kind": "claim",
                "score": None,
                "reason": "not covered",
                "severity": "minor",
            }
        ],
    )
    coverage_summary = kw.pop(
        "coverage_summary",
        {
            "counts": {"grilled": 1, "light": 0, "skipped": 1},
            "jd_must": {"grilled": 0, "light": 0, "skipped": 0},
            "dims": {
                "correctness": 4.0,
                "relevance": 4.0,
                "depth": 3.5,
                "structure": 4.0,
                "honesty": 4.0,
            },
            "topics": [
                {
                    "topic_id": TOPIC_A,
                    "title": "Latency work",
                    "kind": "claim",
                    "coverage": "grilled",
                },
                {
                    "topic_id": TOPIC_B,
                    "title": "Ownership of billing API",
                    "kind": "claim",
                    "coverage": "skipped",
                },
            ],
        },
    )
    claims = kw.pop(
        "claims",
        [
            ReportClaimInput(
                claim_id=CLAIM_A,
                claim_type="metric",
                text="Reduced p99 latency 40% via Redis",
                document_type="resume",
            )
        ],
    )
    turns = kw.pop(
        "turns",
        [
            ReportTurnInput(
                topic_id=TOPIC_A,
                role="user",
                text="I measured p99 in Grafana over two weeks after adding Redis.",
            )
        ],
    )
    corrections = kw.pop("corrections", [])
    assert not kw, f"unexpected kwargs: {sorted(kw)}"
    return ReportAssemblyInput(
        meta=ReportSessionMeta(
            session_id=SESSION,
            duration_minutes=15,
            difficulty="standard",
            seniority="mid",
            resume_filename="resume.pdf",
            jd_filename=jd_filename,
            wrap_reason="user_ended",
        ),
        overall_score=3.5,
        hire_signal="solid",
        strengths=strengths,
        gaps=gaps,
        coverage_summary=coverage_summary,
        topics=topics,
        claims=claims,
        turns=turns,
        corrections=corrections,
    )


def test_assemble_report_validates_against_schema() -> None:
    report = assemble_report(_base_input())
    validated = validate_report_json(report)
    assert validated.schema_version == "v1"
    assert validated.session_meta.session_id == SESSION
    assert validated.prose.summary is None
    assert validated.prose.pros == []


def test_assemble_marks_unscored_topics_insufficient_evidence() -> None:
    report = assemble_report(_base_input())
    by_id = {n["topic_id"]: n for n in report["topic_notes"]}
    assert by_id[TOPIC_B]["insufficient_evidence"] is True
    assert by_id[TOPIC_B]["composite"] is None
    assert by_id[TOPIC_A]["insufficient_evidence"] is False


def test_assemble_does_not_invent_topic_feedback_for_skipped() -> None:
    report = assemble_report(_base_input())
    skipped = next(n for n in report["topic_notes"] if n["topic_id"] == TOPIC_B)
    assert skipped["intents"] == []
    assert skipped["evidence_quotes"] == []
    assert skipped["n_turns"] == 0


def test_assemble_links_resume_claim_to_interview_outcome() -> None:
    report = assemble_report(_base_input())
    notes = report["resume_linked_notes"]
    assert len(notes) == 1
    assert notes[0]["claim_id"] == CLAIM_A
    assert notes[0]["interview_outcome"] == "supported"
    assert "Grafana" in notes[0]["detail"] or "measured" in notes[0]["detail"].lower()


def test_assemble_flags_bluff_as_contradicted_resume_link() -> None:
    topics = [
        ReportTopicInput(
            topic_id=TOPIC_A,
            title="Latency work",
            kind="claim",
            status="scored",
            claim_id=CLAIM_A,
            rollup_scores={
                "coverage": "grilled",
                "composite": 1.5,
                "dims": {
                    "correctness": 2.0,
                    "relevance": 2.0,
                    "depth": 1.0,
                    "structure": 2.0,
                    "honesty": 1.0,
                },
                "flags": {"bluff": 1},
                "n_turns": 1,
            },
            intents=["metric probe"],
            evidence_quotes=[
                {"chunk_id": CHUNK_A, "quote": "Reduced p99 latency 40%", "source": "resume"}
            ],
        )
    ]
    report = assemble_report(_base_input(topics=topics, strengths=[], gaps=[]))
    assert report["resume_linked_notes"][0]["interview_outcome"] == "contradicted"


def test_assemble_jd_alignment_buckets() -> None:
    topics = [
        ReportTopicInput(
            topic_id=TOPIC_A,
            title="Must know Postgres",
            kind="jd_must",
            status="scored",
            claim_id=CLAIM_JD,
            rollup_scores={
                "coverage": "grilled",
                "composite": 4.0,
                "dims": {
                    "correctness": 4.0,
                    "relevance": 4.0,
                    "depth": 4.0,
                    "structure": 4.0,
                    "honesty": 4.0,
                },
                "flags": {},
                "n_turns": 2,
            },
            intents=["postgres indexing"],
            evidence_quotes=[],
        ),
        ReportTopicInput(
            topic_id=TOPIC_B,
            title="Kafka experience",
            kind="jd_must",
            status="scored",
            claim_id=None,
            rollup_scores={
                "coverage": "light",
                "composite": 2.8,
                "dims": {
                    "correctness": 3.0,
                    "relevance": 3.0,
                    "depth": 2.0,
                    "structure": 3.0,
                    "honesty": 4.0,
                },
                "flags": {},
                "n_turns": 1,
            },
            intents=["kafka basics"],
            evidence_quotes=[],
        ),
        ReportTopicInput(
            topic_id=TOPIC_C,
            title="On-call ownership",
            kind="jd_must",
            status="planned",
            claim_id=None,
            rollup_scores={"coverage": "skipped", "composite": None, "flags": {}, "n_turns": 0},
            intents=[],
            evidence_quotes=[],
        ),
    ]
    coverage = {
        "counts": {"grilled": 1, "light": 1, "skipped": 1},
        "jd_must": {"grilled": 1, "light": 1, "skipped": 1},
        "dims": {},
        "topics": [
            {"topic_id": TOPIC_A, "title": "Must know Postgres", "kind": "jd_must", "coverage": "grilled"},
            {"topic_id": TOPIC_B, "title": "Kafka experience", "kind": "jd_must", "coverage": "light"},
            {"topic_id": TOPIC_C, "title": "On-call ownership", "kind": "jd_must", "coverage": "skipped"},
        ],
    }
    report = assemble_report(
        _base_input(
            jd_filename="jd.pdf",
            topics=topics,
            coverage_summary=coverage,
            claims=[
                ReportClaimInput(
                    claim_id=CLAIM_JD,
                    claim_type="skill",
                    text="Postgres required",
                    document_type="jd",
                )
            ],
            strengths=[],
            gaps=[],
            turns=[],
        )
    )
    jd = report["jd_alignment"]
    assert jd is not None
    assert [x["topic_id"] for x in jd["covered"]] == [TOPIC_A]
    assert [x["topic_id"] for x in jd["weak"]] == [TOPIC_B]
    assert [x["topic_id"] for x in jd["missing"]] == [TOPIC_C]


def test_assemble_includes_correction_highlights_in_appendix() -> None:
    report = assemble_report(
        _base_input(
            corrections=[
                ReportCorrectionInput(
                    raw="I used rediss caching",
                    normalized="I used redis caching",
                    replacements=["rediss→redis"],
                )
            ]
        )
    )
    highlights = report["appendix"]["correction_highlights"]
    assert len(highlights) == 1
    assert highlights[0]["replacements"] == ["rediss→redis"]


def test_assemble_leaves_prose_empty_for_llm() -> None:
    report = assemble_report(_base_input())
    assert report["prose"] == {
        "summary": None,
        "pros": [],
        "cons": [],
        "next_steps": [],
    }
    assert report["overall_signal"]["summary"] is None
