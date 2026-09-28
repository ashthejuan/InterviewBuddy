"""Heuristic claim extraction (no LLM)."""

from __future__ import annotations

import uuid

from app.services.claims import ChunkRef, extract_claims_heuristic


def test_extracts_metric_and_skill_claims() -> None:
    cid_metric = uuid.uuid4()
    cid_skill = uuid.uuid4()
    chunks = [
        ChunkRef(id=cid_metric, content="Reduced p99 latency 40% via caching", section_kind="experience"),
        ChunkRef(id=cid_skill, content="Python", section_kind="skills"),
        ChunkRef(id=uuid.uuid4(), content="Owned on-call for payments", section_kind="experience"),
    ]
    claims = extract_claims_heuristic(chunks)
    types = {c.claim_type for c in claims}
    assert "metric" in types
    assert "skill" in types
    assert "ownership" in types
    metric = next(c for c in claims if c.claim_type == "metric")
    assert cid_metric in metric.source_chunk_ids
