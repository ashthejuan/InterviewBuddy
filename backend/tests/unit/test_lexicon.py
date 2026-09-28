"""Session lexicon builder."""

from __future__ import annotations

from app.services.lexicon import build_lexicon


def test_build_lexicon_collects_skills_tools_companies_metrics() -> None:
    lexicon = build_lexicon(
        claim_texts=[
            "Reduced p99 latency 40% via caching",
            "Led team of 5 at Acme Corp",
            "Python FastAPI expert",
        ],
        chunk_texts=[
            "Acme Corp — Senior Engineer",
            "Postgres, Redis, Kubernetes",
        ],
    )
    assert "skills" in lexicon
    assert "tools" in lexicon
    assert "companies" in lexicon
    assert "metrics" in lexicon
    assert any("40%" in m or "40" in m for m in lexicon["metrics"])
    assert "Acme Corp" in lexicon["companies"] or any("Acme" in c for c in lexicon["companies"])
