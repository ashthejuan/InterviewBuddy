"""DEFAULT_GRILL_MODEL is the single model for all LLM jobs."""

from __future__ import annotations

from app.config import Settings


def test_all_llm_jobs_use_default_grill_model() -> None:
    s = Settings(default_grill_model="acme/model-x")
    assert s.grill_model == "acme/model-x"
    assert s.score_model == "acme/model-x"
    assert s.report_model == "acme/model-x"
    assert s.claims_model == "acme/model-x"
