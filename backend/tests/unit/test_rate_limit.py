"""Unit: in-memory rate limiter."""

from __future__ import annotations

from app.rate_limit import MemoryRateLimiter


def test_allows_under_limit() -> None:
    limiter = MemoryRateLimiter(limit=3, window_seconds=60)
    assert limiter.check("u1").allowed
    assert limiter.check("u1").allowed
    assert limiter.check("u1").allowed


def test_blocks_over_limit() -> None:
    limiter = MemoryRateLimiter(limit=2, window_seconds=60)
    assert limiter.check("u2").allowed
    assert limiter.check("u2").allowed
    blocked = limiter.check("u2")
    assert not blocked.allowed
    assert blocked.retry_after_seconds >= 1


def test_keys_are_isolated() -> None:
    limiter = MemoryRateLimiter(limit=1, window_seconds=60)
    assert limiter.check("a").allowed
    assert not limiter.check("a").allowed
    assert limiter.check("b").allowed
