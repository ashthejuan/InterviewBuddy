"""In-memory fixed-window rate limiter (single-process / local MVP)."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass

import structlog
from fastapi import HTTPException, Request, status

log = structlog.get_logger()


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class MemoryRateLimiter:
    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, *, now: float | None = None) -> RateLimitDecision:
        t = time.monotonic() if now is None else now
        cutoff = t - self.window_seconds
        prev = [ts for ts in self._hits[key] if ts > cutoff]
        if len(prev) >= self.limit:
            oldest = prev[0] if prev else t
            retry = max(1, int(oldest + self.window_seconds - t) + 1)
            self._hits[key] = prev
            return RateLimitDecision(allowed=False, retry_after_seconds=retry)
        prev.append(t)
        self._hits[key] = prev
        return RateLimitDecision(allowed=True)


# Per authenticated user (or IP fallback).
upload_limiter = MemoryRateLimiter(limit=30, window_seconds=60)
answer_limiter = MemoryRateLimiter(limit=60, window_seconds=60)
voice_token_limiter = MemoryRateLimiter(limit=20, window_seconds=60)
report_retry_limiter = MemoryRateLimiter(limit=10, window_seconds=60)


def client_key(request: Request, user_id: str | None = None) -> str:
    if user_id:
        return f"user:{user_id}"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    if request.client:
        return f"ip:{request.client.host}"
    return "ip:unknown"


def enforce(limiter: MemoryRateLimiter, key: str, *, route: str) -> None:
    decision = limiter.check(key)
    if decision.allowed:
        return
    log.warning(
        "rate_limited",
        route=route,
        key=key,
        retry_after=decision.retry_after_seconds,
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="rate limit exceeded — try again shortly",
        headers={"Retry-After": str(decision.retry_after_seconds)},
    )
