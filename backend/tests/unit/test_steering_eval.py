"""Unit: steering evaluation helpers (agreement vs LLM rubric, length-controlled fixtures)."""

from __future__ import annotations

from app.services.steering_eval import LENGTH_FIXTURES, agreement_by_length, length_bucket


def test_length_buckets() -> None:
    assert length_bucket("one two three") == "<25"
    assert length_bucket(" ".join(["w"] * 40)) == "25-59"
    assert length_bucket(" ".join(["w"] * 80)) == "60-119"
    assert length_bucket(" ".join(["w"] * 200)) == "120+"


def test_agreement_by_length_counts_matches_and_confusions() -> None:
    rows = [
        ("short", "deepen", "deepen"),
        ("short", "scorable", "deepen"),
        ("long", None, "scorable"),
    ]
    table = agreement_by_length(rows)
    assert table["short"]["n"] == 2
    assert table["short"]["agree"] == 1
    assert table["short"]["rate"] == 0.5
    assert table["short"]["confusion"] == {"deepen→deepen": 1, "scorable→deepen": 1}
    assert table["long"]["confusion"] == {"none→scorable": 1}
    assert table["all"]["n"] == 3


def test_length_fixtures_differ_only_in_padding() -> None:
    assert len(LENGTH_FIXTURES) >= 4
    for fx in LENGTH_FIXTURES:
        assert fx.expected in ("probe", "deepen", "scorable", None)
        assert len(fx.padded.split()) >= 3 * len(fx.terse.split()), fx.name
