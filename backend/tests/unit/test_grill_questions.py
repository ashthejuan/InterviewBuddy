"""Tests for grill question cleanup helpers."""

from __future__ import annotations

from app.services.grill_questions import _clean_question


def test_clean_question_strips_label_and_quotes() -> None:
    assert _clean_question('Question: "What did you own?"') == "What did you own?"
    assert _clean_question("Q - Tell me more.\n\nExtra paragraph") == "Tell me more."
