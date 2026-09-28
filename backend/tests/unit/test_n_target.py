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
    # T_core ≈ 5 → N_max = 1; when N_min > N_max, use N_max
    assert n == 1
