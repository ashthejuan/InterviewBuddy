"""Pure grill policy helpers (PRD §5 / §8). No DB / LLM."""

from __future__ import annotations

import re
from typing import Any

_IDK_RE = re.compile(
    r"\b("
    r"i\s*don'?t\s*know|"
    r"i\s*do\s*not\s*know|"
    r"idk|"
    r"no\s*idea|"
    r"not\s*sure|"
    r"i'?m\s*not\s*sure"
    r")\b",
    re.IGNORECASE,
)


def looks_like_idk(text: str) -> bool:
    return bool(_IDK_RE.search(text.strip()))


def should_exit_topic(
    *,
    seconds_spent: int,
    soft_cap: int,
    hard_cap: int,
    followups_used: int,
    max_followups: int,
    answer_is_idk: bool,
    topics_left: int,
    time_left_seconds: int,
) -> tuple[bool, str]:
    if answer_is_idk:
        return True, "idk"
    if seconds_spent >= hard_cap:
        return True, "hard_cap"
    if followups_used >= max_followups:
        return True, "followups_exhausted"
    if (
        topics_left > 0
        and soft_cap > 0
        and topics_left > (time_left_seconds / soft_cap)
    ):
        return True, "coverage_pressure"
    if seconds_spent >= soft_cap:
        return True, "soft_cap"
    return False, ""


def apply_score_signal(
    exit_: bool,
    reason: str,
    *,
    signal: str | None,
    seconds_spent: int,
    soft_cap: int,
    followups_used: int,
    max_followups: int,
    topics_left: int,
    time_left_seconds: int,
) -> tuple[bool, str, str | None]:
    """Let rubric output steer the frontier. Returns (exit, reason, directive).

    probe    — bluff/contradiction: one evidence probe, even past the follow-up budget.
    deepen   — shallow but on-topic: one deepen, only while breadth is on pace.
    scorable — enough evidence + time pressure: rotate now.
    IDK and hard cap always win.
    """
    if reason in ("idk", "hard_cap") or signal is None:
        return exit_, reason, None
    extra_ok = followups_used < max_followups + 1
    if signal == "probe" and extra_ok:
        return False, "", "probe"
    if signal == "deepen":
        if not exit_:
            return False, "", "deepen"
        if reason == "followups_exhausted" and extra_ok and seconds_spent < soft_cap:
            return False, "", "deepen"
    if signal == "scorable" and not exit_ and topics_left > 0:
        time_pressure = (
            seconds_spent * 2 >= soft_cap
            or topics_left * soft_cap >= 0.75 * time_left_seconds
        )
        if time_pressure:
            return True, "scorable", None
    return exit_, reason, None


def pick_next_topic(topics: list[dict[str, Any]]) -> dict[str, Any] | None:
    planned = [t for t in topics if t.get("status") == "planned"]
    if not planned:
        return None
    warmups = [t for t in planned if t.get("kind") == "warmup"]
    if warmups:
        return warmups[0]
    return max(planned, key=lambda t: (int(t.get("priority") or 0), str(t.get("title") or "")))


def stub_question(
    *,
    title: str,
    intent: str | None,
    mode: str,
    followup: bool,
    directive: str | None = None,
) -> str:
    subject = (intent or title).strip() or "this topic"
    if directive == "probe":
        return (
            f"I want to pin that down against your resume on {subject}. "
            "What concrete evidence backs it — the actual numbers, how you measured them, "
            "and what you personally did?"
        )
    if directive == "deepen":
        return (
            f"Go one level deeper on {subject}: what were the key tradeoffs, "
            "what broke along the way, and what would you do differently?"
        )
    if followup or mode == "escalate":
        return (
            f"Can you walk me through a concrete example related to {subject}? "
            "What specifically did you own end to end?"
        )
    if mode == "direct":
        return (
            f"You mentioned {subject}. What was your specific contribution, "
            "and how did you measure the result?"
        )
    # parallel / default
    return (
        f"Tell me about your experience with {subject}. "
        "What did you work on, and what was hard about it?"
    )
