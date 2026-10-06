"""Shared OpenRouter chat helpers for grill + scorer."""

from __future__ import annotations

from typing import Any


def grill_completion_options() -> dict[str, Any]:
    """One spoken question — no reasoning budget; short visible output."""
    return {
        "max_tokens": 200,
        "reasoning": {"effort": "none"},
    }


def score_completion_options() -> dict[str, Any]:
    """Rubric JSON — reasoning off (this model otherwise exhausts max_tokens thinking)."""
    return {
        "max_tokens": 400,
        "reasoning": {"effort": "none"},
    }


def message_text(data: dict[str, Any]) -> str:
    """Return stripped assistant content; raise if missing (e.g. reasoning ate budget)."""
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("empty content: no choices in OpenRouter response")
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if content is None or not str(content).strip():
        finish = choices[0].get("finish_reason")
        raise ValueError(f"empty content: finish_reason={finish!r}")
    return str(content).strip()
