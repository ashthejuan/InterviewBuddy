#!/usr/bin/env python3
"""Generate a sample Phase 6 report and save it under repo `reports/`.

Usage (from backend/):
  uv run python scripts/generate_sample_report.py

Uses heuristic prose (no OpenRouter). Does not require Postgres.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Allow `uv run python scripts/...` without installing as a package entrypoint.
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("REPORT_BACKEND", "heuristic")

from app.config import get_settings
from app.services.report import (
    ReportAssemblyInput,
    ReportClaimInput,
    ReportCorrectionInput,
    ReportSessionMeta,
    ReportTopicInput,
    ReportTurnInput,
    assemble_report,
)
from app.services.report_export import write_report_files
from app.services.report_markdown import render_report_markdown
from app.services.report_prose import fill_prose

TOPIC_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TOPIC_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
TOPIC_C = "cccccccc-cccc-cccc-cccc-cccccccccccc"
CLAIM_A = "dddddddd-dddd-dddd-dddd-dddddddddddd"
CHUNK_A = "ffffffff-ffff-ffff-ffff-ffffffffffff"
SESSION = "11111111-1111-1111-1111-111111111111"


def _sample_input() -> ReportAssemblyInput:
    return ReportAssemblyInput(
        meta=ReportSessionMeta(
            session_id=SESSION,
            duration_minutes=15,
            difficulty="medium",
            seniority="mid",
            resume_filename="sample-resume.pdf",
            jd_filename="sample-jd.pdf",
            wrap_reason="user_ended",
        ),
        overall_score=3.4,
        hire_signal="solid",
        strengths=[
            {
                "topic_id": TOPIC_A,
                "title": "Latency work",
                "kind": "claim",
                "score": 3.8,
                "reason": "strong depth",
            }
        ],
        gaps=[
            {
                "topic_id": TOPIC_B,
                "title": "Kafka ownership",
                "kind": "jd_must",
                "score": 2.1,
                "reason": "weak depth",
                "severity": "major",
            },
            {
                "topic_id": TOPIC_C,
                "title": "On-call ownership",
                "kind": "jd_must",
                "score": None,
                "reason": "not covered",
                "severity": "minor",
            },
        ],
        coverage_summary={
            "counts": {"grilled": 1, "light": 1, "skipped": 1},
            "jd_must": {"grilled": 0, "light": 1, "skipped": 1},
            "dims": {
                "correctness": 3.5,
                "relevance": 3.6,
                "depth": 3.1,
                "structure": 3.4,
                "honesty": 3.8,
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
                    "title": "Kafka ownership",
                    "kind": "jd_must",
                    "coverage": "light",
                },
                {
                    "topic_id": TOPIC_C,
                    "title": "On-call ownership",
                    "kind": "jd_must",
                    "coverage": "skipped",
                },
            ],
        },
        topics=[
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
                        "quote": "Reduced p99 latency 40% via Redis caching",
                        "source": "resume",
                    }
                ],
            ),
            ReportTopicInput(
                topic_id=TOPIC_B,
                title="Kafka ownership",
                kind="jd_must",
                status="scored",
                claim_id=None,
                rollup_scores={
                    "coverage": "light",
                    "composite": 2.1,
                    "dims": {
                        "correctness": 2.0,
                        "relevance": 3.0,
                        "depth": 1.5,
                        "structure": 2.0,
                        "honesty": 4.0,
                    },
                    "flags": {},
                    "n_turns": 1,
                },
                intents=["kafka consumer lag"],
                evidence_quotes=[],
            ),
            ReportTopicInput(
                topic_id=TOPIC_C,
                title="On-call ownership",
                kind="jd_must",
                status="skipped",
                claim_id=None,
                rollup_scores={
                    "coverage": "skipped",
                    "composite": None,
                    "flags": {},
                    "n_turns": 0,
                },
                intents=[],
                evidence_quotes=[],
            ),
        ],
        claims=[
            ReportClaimInput(
                claim_id=CLAIM_A,
                claim_type="metric",
                text="Reduced p99 latency 40% via Redis caching",
                document_type="resume",
            )
        ],
        turns=[
            ReportTurnInput(
                topic_id=TOPIC_A,
                role="user",
                text="I measured p99 in Grafana over two weeks after adding Redis.",
            ),
            ReportTurnInput(
                topic_id=TOPIC_B,
                role="user",
                text="We used Kafka but I wasn't deep on the consumer side.",
            ),
        ],
        corrections=[
            ReportCorrectionInput(
                raw="I used rediss caching",
                normalized="I used redis caching",
                replacements=["rediss→redis"],
            )
        ],
    )


async def main() -> int:
    get_settings.cache_clear()
    assembled = assemble_report(_sample_input())
    filled = await fill_prose(assembled)
    md = render_report_markdown(filled)
    paths = write_report_files(report_json=filled, report_markdown=md, session_id=SESSION)
    print(f"Wrote {paths.markdown}")
    print(f"Wrote {paths.json_path}")
    print(f"Hire signal: {filled['overall_signal']['hire_signal']}")
    print(f"Summary: {filled['prose']['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
