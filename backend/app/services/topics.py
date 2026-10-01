"""Topic planning + N_target (PRD §5)."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass


@dataclass
class ClaimSeed:
    claim_id: uuid.UUID | None
    title: str
    kind: str  # jd_must | claim | behavioral | warmup
    priority: int
    measurable: bool


@dataclass
class PlannedTopic:
    title: str
    kind: str
    priority: int
    claim_id: uuid.UUID | None
    question_mode: str  # parallel | direct | escalate
    soft_cap_seconds: int = 210
    hard_cap_seconds: int = 330


@dataclass
class TopicPlan:
    n_target: int
    topics: list[PlannedTopic]


def compute_n_target(*, duration_minutes: int, priority_count: int) -> int:
    # Short sessions use tighter slots so 15m still covers several topics.
    soft_cap_min = 3.5 if duration_minutes >= 25 else 2.5
    overhead = 5.0 if duration_minutes >= 25 else 2.0
    t_core_min = max(soft_cap_min, float(duration_minutes) - overhead)
    n_max = max(1, int(t_core_min // soft_cap_min))
    floor_min = 3 if duration_minutes >= 20 else 2
    n_min = max(floor_min, math.ceil(0.5 * n_max))
    if n_min > n_max:
        return n_max
    return max(n_min, min(n_max, priority_count))


def _caps_for(*, kind: str, duration_minutes: int) -> tuple[int, int]:
    if kind == "warmup":
        return 120, 180
    if duration_minutes < 25:
        return 150, 240
    return 210, 330


def plan_topics(
    *,
    duration_minutes: int,
    jd_seeds: list[ClaimSeed],
    claim_seeds: list[ClaimSeed],
) -> TopicPlan:
    candidates: list[ClaimSeed] = []
    candidates.append(
        ClaimSeed(claim_id=None, title="Warmup intro", kind="warmup", priority=0, measurable=False)
    )
    candidates.extend(sorted(jd_seeds, key=lambda s: -s.priority))
    candidates.extend(sorted(claim_seeds, key=lambda s: -s.priority))
    candidates.append(
        ClaimSeed(
            claim_id=None,
            title="Behavioral: conflict or tradeoff",
            kind="behavioral",
            priority=10,
            measurable=False,
        )
    )

    # Deduplicate by title
    seen: set[str] = set()
    unique: list[ClaimSeed] = []
    for s in candidates:
        key = s.title.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(s)

    priority_count = len([s for s in unique if s.kind != "warmup"])
    n_target = compute_n_target(
        duration_minutes=duration_minutes, priority_count=max(priority_count, 1)
    )

    # Always keep warmup first, then fill to n_target
    warmup = unique[0]
    rest = unique[1:]
    chosen = [warmup] + rest[: max(0, n_target - 1)]
    # If still short, pad with behavioral variants
    i = 2
    while len(chosen) < n_target:
        chosen.append(
            ClaimSeed(
                claim_id=None,
                title=f"Behavioral follow-up {i}",
                kind="behavioral",
                priority=5,
                measurable=False,
            )
        )
        i += 1

    topics: list[PlannedTopic] = []
    for s in chosen[:n_target]:
        mode = "direct" if s.measurable else "parallel"
        soft, hard = _caps_for(kind=s.kind, duration_minutes=duration_minutes)
        topics.append(
            PlannedTopic(
                title=s.title[:200],
                kind=s.kind,
                priority=s.priority,
                claim_id=s.claim_id,
                question_mode=mode,
                soft_cap_seconds=soft,
                hard_cap_seconds=hard,
            )
        )
    return TopicPlan(n_target=n_target, topics=topics)
