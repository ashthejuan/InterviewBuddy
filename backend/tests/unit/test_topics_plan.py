"""Topic planning + frontier seed helpers."""

from __future__ import annotations

import uuid

from app.services.topics import ClaimSeed, plan_topics


def test_plan_topics_priority_jd_then_claims_then_behavioral() -> None:
    jd = ClaimSeed(
        claim_id=uuid.uuid4(),
        title="Must have Postgres",
        kind="jd_must",
        priority=100,
        measurable=True,
    )
    claim = ClaimSeed(
        claim_id=uuid.uuid4(),
        title="Reduced latency 40%",
        kind="claim",
        priority=50,
        measurable=True,
    )
    planned = plan_topics(
        duration_minutes=30,
        jd_seeds=[jd],
        claim_seeds=[claim],
    )
    assert planned.n_target >= 3
    kinds = [t.kind for t in planned.topics]
    assert kinds[0] == "warmup"
    assert "jd_must" in kinds
    assert "claim" in kinds
    assert "behavioral" in kinds
    assert len(planned.topics) == planned.n_target
