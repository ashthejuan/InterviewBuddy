"""Steering evaluation helpers — agreement vs the LLM rubric, bucketed by answer length.

Used by `scripts/eval_steering.py`. No DB / LLM here.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

_BUCKETS = ((25, "<25"), (60, "25-59"), (120, "60-119"))


def length_bucket(text: str) -> str:
    n = len((text or "").split())
    for upper, label in _BUCKETS:
        if n < upper:
            return label
    return "120+"


def _label(signal: str | None) -> str:
    return signal or "none"


def agreement_by_length(
    rows: Iterable[tuple[str, str | None, str | None]],
) -> dict[str, dict[str, Any]]:
    """rows: (bucket, reference signal, candidate signal) → per-bucket + "all" agreement."""
    groups: dict[str, list[tuple[str | None, str | None]]] = {}
    for bucket, ref, cand in rows:
        groups.setdefault(bucket, []).append((ref, cand))
        groups.setdefault("all", []).append((ref, cand))
    table: dict[str, dict[str, Any]] = {}
    for bucket, pairs in groups.items():
        agree = sum(1 for ref, cand in pairs if ref == cand)
        table[bucket] = {
            "n": len(pairs),
            "agree": agree,
            "rate": round(agree / len(pairs), 3),
            "confusion": dict(Counter(f"{_label(r)}→{_label(c)}" for r, c in pairs)),
        }
    return table


@dataclass(frozen=True)
class LengthFixture:
    """Same content said tersely and padded — a content-based steer gives both one signal."""

    name: str
    question: str
    evidence: str
    terse: str
    padded: str
    expected: str | None


_FILLER = (
    "So, yeah, I mean, to give you the full picture here, this was a pretty big part of what "
    "the team was doing at the time, and there were a lot of moving pieces and a lot of people "
    "involved, so it is kind of hard to summarise it all, but I will try to walk you through it "
    "as best I can and give you the general sense of how it all came together for us. "
)

LENGTH_FIXTURES: list[LengthFixture] = [
    LengthFixture(
        name="precise_sharding",
        question="How did you shard the ledger tables?",
        evidence="Sharded the Postgres ledger to support 10x write volume.",
        terse=(
            "Hash on account_id into 64 shards, virtual nodes so a rebalance moves about a "
            "sixty-fourth of keys, and cross-shard transfers go through a two-phase outbox."
        ),
        padded=_FILLER
        + "Basically we hashed on account_id into 64 shards. "
        + _FILLER
        + "We used virtual nodes so a rebalance only moves about a sixty-fourth of the keys, "
        "and the cross-shard transfers went through a two-phase outbox. "
        + _FILLER,
        expected="scorable",
    ),
    LengthFixture(
        name="shallow_caching",
        question="How did the caching layer cut latency?",
        evidence="Reduced p99 latency 40% via Redis caching.",
        terse="We added caching and it made things faster.",
        padded=_FILLER
        + "We added caching, and honestly caching is really important for performance, "
        "everyone knows that, and it made things a lot faster for the users. "
        + _FILLER
        + "It was faster after that, and the team was happy with how fast it got.",
        expected="deepen",
    ),
    LengthFixture(
        name="metric_bluff",
        question="What did the Redis cache do for latency?",
        evidence="Reduced p99 latency 40% via Redis caching.",
        terse="I cut p99 latency by 90% with the Redis cache.",
        padded=_FILLER
        + "The main thing is that I personally cut p99 latency by 90% with the Redis cache. "
        + _FILLER
        + "So yeah, 90% lower p99, that was the outcome.",
        expected="probe",
    ),
    LengthFixture(
        name="spoken_filler_precise",
        question="How did you handle cache invalidation?",
        evidence="Reduced p99 latency 40% via Redis caching.",
        terse=(
            "Um, you know, we kind of keyed entries on plan version, so invalidation is just "
            "a version bump, and hit rate held at 93 percent in Grafana."
        ),
        padded=_FILLER
        + "Um, you know, we kind of keyed the entries on the plan version. "
        + _FILLER
        + "So invalidation was just a version bump, and the hit rate held at 93 percent in "
        "Grafana over two weeks. "
        + _FILLER,
        expected="scorable",
    ),
    LengthFixture(
        name="percent_of_time_not_bluff",
        question="What did owning payments on-call involve?",
        evidence="Owned payments on-call; reduced p99 latency 40%.",
        terse=(
            "About 90% of my time was on-call; I rewrote the runbook and cut pages from 30 to "
            "8 a week by fixing two flaky alerts."
        ),
        padded=_FILLER
        + "About 90% of my time was on-call for payments. "
        + _FILLER
        + "I rewrote the runbook and cut pages from 30 to 8 a week by fixing two flaky alerts. "
        + _FILLER,
        expected="scorable",
    ),
]
