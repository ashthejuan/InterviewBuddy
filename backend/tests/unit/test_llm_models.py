"""DEFAULT_GRILL_MODEL resolves all LLM job models."""

from __future__ import annotations

from app.config import Settings


def test_empty_overrides_use_default_grill_model() -> None:
    s = Settings(
        default_grill_model="qwen/qwen3.7-flash",
        openrouter_grill_model="",
        openrouter_score_model="",
        openrouter_report_model="",
        openrouter_claims_model="",
    )
    assert s.grill_model == "qwen/qwen3.7-flash"
    assert s.score_model == "qwen/qwen3.7-flash"
    assert s.report_model == "qwen/qwen3.7-flash"
    assert s.claims_model == "qwen/qwen3.7-flash"


def test_per_job_override_wins() -> None:
    s = Settings(
        default_grill_model="qwen/qwen3.7-flash",
        openrouter_claims_model="qwen/qwen3.7-plus",
    )
    assert s.claims_model == "qwen/qwen3.7-plus"
    assert s.grill_model == "qwen/qwen3.7-flash"
