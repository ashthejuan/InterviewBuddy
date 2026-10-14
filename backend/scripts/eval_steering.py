#!/usr/bin/env python3
"""Evaluate the grill steering signal against content, not length.

Usage (from backend/):
  # Length-controlled fixtures: terse vs padded answers with the same content
  uv run python scripts/eval_steering.py fixtures [--classifier]

  # Agreement with the stored LLM rubric on real turns (Postgres required)
  uv run python scripts/eval_steering.py sessions [--limit 20] [--classifier]

`--classifier` calls OpenRouter once per answer (uses OPENROUTER_API_KEY / STEER_MODEL).
The reference in `sessions` mode is `score_signal` of each turn's stored LLM rubric score.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import select

from app.db import SessionLocal
from app.models import InterviewSession, SessionTopic, Turn, TurnScore
from app.services import scorer
from app.services.grill_prompt import RetrievedChunk
from app.services.scoring import TurnScoreDraft, heuristic_score, score_signal
from app.services.steering_eval import LENGTH_FIXTURES, agreement_by_length, length_bucket


def _heuristic_signal(*, question: str, answer: str, evidence: list[RetrievedChunk], kind: str):
    draft = heuristic_score(question=question, answer=answer, evidence=evidence)
    return score_signal(draft, kind=kind)


async def _classifier_signal(
    *,
    session: InterviewSession,
    topic: SessionTopic,
    question: str,
    answer: str,
    prior_answer: str | None,
    evidence: list[RetrievedChunk],
) -> tuple[str | None, int]:
    started = time.perf_counter()
    try:
        signal = await scorer._classify_openrouter(
            session=session,
            topic=topic,
            question=question,
            answer=answer,
            prior_answer=prior_answer,
            evidence=evidence,
        )
    except Exception as exc:  # noqa: BLE001 — report, keep evaluating
        signal = f"error:{type(exc).__name__}"
    return signal, round((time.perf_counter() - started) * 1000)


async def run_fixtures(use_classifier: bool) -> int:
    session = InterviewSession(settings={"seniority": "mid"})
    sensitive = 0
    for fx in LENGTH_FIXTURES:
        evidence = [RetrievedChunk(id=uuid.uuid4(), content=fx.evidence)]
        topic = SessionTopic(title=fx.question, kind="claim")
        row: dict[str, object] = {"fixture": fx.name, "expected": fx.expected}
        for variant in ("terse", "padded"):
            answer = getattr(fx, variant)
            row[f"heuristic_{variant}"] = _heuristic_signal(
                question=fx.question, answer=answer, evidence=evidence, kind="claim"
            )
            if use_classifier:
                signal, ms = await _classifier_signal(
                    session=session,
                    topic=topic,
                    question=fx.question,
                    answer=answer,
                    prior_answer=None,
                    evidence=evidence,
                )
                row[f"classifier_{variant}"] = signal
                row[f"classifier_{variant}_ms"] = ms
        for source in ("heuristic", "classifier"):
            if f"{source}_terse" in row and row[f"{source}_terse"] != row[f"{source}_padded"]:
                row[f"{source}_length_sensitive"] = True
                sensitive += 1
        print(json.dumps(row))
    print(json.dumps({"length_sensitive_pairs": sensitive, "fixtures": len(LENGTH_FIXTURES)}))
    return 0


async def run_sessions(limit: int, use_classifier: bool) -> int:
    heuristic_rows: list[tuple[str, str | None, str | None]] = []
    classifier_rows: list[tuple[str, str | None, str | None]] = []
    latencies: list[int] = []
    async with SessionLocal() as db:
        sessions = (
            await db.execute(
                select(InterviewSession)
                .where(InterviewSession.status == "completed")
                .order_by(InterviewSession.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        for session in sessions:
            turns = (
                await db.execute(
                    select(Turn)
                    .where(Turn.session_id == session.id)
                    .order_by(Turn.created_at, Turn.id)
                )
            ).scalars().all()
            last_question = ""
            prior_by_topic: dict[uuid.UUID, str] = {}
            for turn in turns:
                if turn.role == "agent":
                    last_question = turn.raw_text
                    continue
                answer = turn.normalized_text or turn.raw_text
                score = await db.scalar(select(TurnScore).where(TurnScore.turn_id == turn.id))
                topic = await db.get(SessionTopic, turn.topic_id) if turn.topic_id else None
                prior = prior_by_topic.get(turn.topic_id) if turn.topic_id else None
                if turn.topic_id:
                    prior_by_topic[turn.topic_id] = answer
                if (
                    topic is None
                    or score is None
                    or topic.kind == "warmup"
                    or (score.rationale or "").startswith(scorer.HEURISTIC_RATIONALE_PREFIX)
                ):
                    continue
                reference = score_signal(
                    TurnScoreDraft(
                        correctness=score.correctness,
                        relevance=score.relevance,
                        depth=score.depth,
                        structure=score.structure,
                        honesty=score.honesty,
                        confidence=score.confidence if score.confidence is not None else 0.5,
                        rationale=score.rationale or "",
                        flags=dict(score.flags or {}),
                    ),
                    kind=topic.kind,
                )
                evidence = await scorer.gather_evidence(
                    db, session, topic, intent=topic.title, answer=answer
                )
                bucket = length_bucket(answer)
                heuristic_rows.append(
                    (
                        bucket,
                        reference,
                        _heuristic_signal(
                            question=last_question,
                            answer=answer,
                            evidence=evidence,
                            kind=topic.kind,
                        ),
                    )
                )
                if use_classifier:
                    signal, ms = await _classifier_signal(
                        session=session,
                        topic=topic,
                        question=last_question,
                        answer=answer,
                        prior_answer=prior,
                        evidence=evidence,
                    )
                    classifier_rows.append((bucket, reference, signal))
                    latencies.append(ms)

    out: dict[str, object] = {
        "sessions": len(sessions),
        "heuristic_vs_llm": agreement_by_length(heuristic_rows),
    }
    if use_classifier:
        out["classifier_vs_llm"] = agreement_by_length(classifier_rows)
        if latencies:
            ordered = sorted(latencies)
            out["classifier_ms"] = {
                "p50": ordered[len(ordered) // 2],
                "p95": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
                "over_cap": sum(1 for ms in latencies if ms > scorer.STEER_TIMEOUT_SECONDS * 1000),
            }
    print(json.dumps(out, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    fx = sub.add_parser("fixtures")
    fx.add_argument("--classifier", action="store_true")
    ss = sub.add_parser("sessions")
    ss.add_argument("--limit", type=int, default=20)
    ss.add_argument("--classifier", action="store_true")
    args = parser.parse_args()
    if args.mode == "fixtures":
        return asyncio.run(run_fixtures(args.classifier))
    return asyncio.run(run_sessions(args.limit, args.classifier))


if __name__ == "__main__":
    raise SystemExit(main())
