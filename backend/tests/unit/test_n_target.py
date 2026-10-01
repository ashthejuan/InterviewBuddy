"""Unit tests for topic N_target formula (PRD §5)."""

from __future__ import annotations

from app.services.topics import compute_n_target


def test_n_target_30_min_with_many_priorities() -> None:
    # T_core ≈ 25, soft 3.5 → N_max ≈ 7; N_min ≈ 4
    n = compute_n_target(duration_minutes=30, priority_count=20)
    assert n == 7


def test_n_target_clamps_up_when_few_priorities() -> None:
    n = compute_n_target(duration_minutes=30, priority_count=1)
    assert n == 4  # N_min


def test_n_target_short_session() -> None:
    n = compute_n_target(duration_minutes=10, priority_count=10)
    # Short slots (~2.5m) so a 10m grill still covers a few topics
    assert n >= 2


def test_n_target_15_min_covers_several_topics() -> None:
    n = compute_n_target(duration_minutes=15, priority_count=10)
    # 15m was collapsing to 2 (warmup + 1) and wrapping ~6m early
    assert n >= 4
