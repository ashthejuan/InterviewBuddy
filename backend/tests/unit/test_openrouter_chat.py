"""OpenRouter chat body + content extraction for grill/scorer."""

from __future__ import annotations

import pytest

from app.services.openrouter_chat import (
    grill_completion_options,
    message_text,
    score_completion_options,
)


def test_grill_disables_reasoning_and_caps_at_200() -> None:
    opts = grill_completion_options()
    assert opts["max_tokens"] == 200
    assert opts["reasoning"] == {"effort": "none"}


def test_score_disables_reasoning_and_caps_at_400() -> None:
    opts = score_completion_options()
    assert opts["max_tokens"] == 400
    assert opts["reasoning"] == {"effort": "none"}


def test_message_text_reads_content() -> None:
    assert message_text({"choices": [{"message": {"content": "  Hello?  "}}]}) == "Hello?"


def test_message_text_rejects_null_content() -> None:
    with pytest.raises(ValueError, match="empty content"):
        message_text(
            {
                "choices": [
                    {
                        "message": {"content": None, "reasoning": "thinking…"},
                        "finish_reason": "length",
                    }
                ]
            }
        )
