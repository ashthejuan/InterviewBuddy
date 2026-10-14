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

_EXPERIENCE_PREFIX = re.compile(
    r"^(hands[-\s]?on\s+)?experience\s+with\s+",
    re.IGNORECASE,
)
_MUST_HAVE_PREFIX = re.compile(r"^must\s+have\s+", re.IGNORECASE)

# JD bullets often start with imperatives; turn them into spoken noun phrases.
_IMPERATIVE_GERUNDS: tuple[tuple[str, str], ...] = (
    ("implement ", "implementing "),
    ("integrate ", "integrating "),
    ("own ", "owning "),
    ("build ", "building "),
    ("design ", "designing "),
    ("develop ", "developing "),
    ("create ", "creating "),
    ("write ", "writing "),
    ("maintain ", "maintaining "),
    ("improve ", "improving "),
    ("optimize ", "optimizing "),
    ("translate ", "translating "),
    ("extend ", "extending "),
    ("ship ", "shipping "),
    ("collaborate ", "collaborating "),
    ("work with ", "working with "),
)


def looks_like_idk(text: str) -> bool:
    return bool(_IDK_RE.search(text.strip()))


def humanize_topic_subject(raw: str | None) -> str:
    """Turn JD/resume topic titles into natural spoken English subjects."""
    s = (raw or "").strip()
    if not s:
        return "this area"
    s = _EXPERIENCE_PREFIX.sub("", s).strip()
    s = _MUST_HAVE_PREFIX.sub("", s).strip()
    if not s:
        return "this area"
    low = s.lower()
    for prefix, gerund in _IMPERATIVE_GERUNDS:
        if low.startswith(prefix):
            rest = s[len(prefix) :].strip()
            return f"{gerund}{rest}".strip()
    return s


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


def merge_lagged_signal(
    current: str | None, lagged: str | None, *, last_directive: str | None
) -> str | None:
    """Fold the previous same-topic answer's LLM signal into the current steering signal.

    The current answer wins, except: a missed integrity issue earns one probe (unless the last
    question already probed), and a topic with a solid scored answer may rotate when the
    current answer gives no signal.
    """
    if current == "probe":
        return current
    if lagged == "probe" and last_directive != "probe":
        return "probe"
    if current is None and lagged == "scorable":
        return "scorable"
    return current


def pick_next_topic(topics: list[dict[str, Any]]) -> dict[str, Any] | None:
    planned = [t for t in topics if t.get("status") == "planned"]
    if not planned:
        return None
    warmups = [t for t in planned if t.get("kind") == "warmup"]
    if warmups:
        return warmups[0]
    return max(planned, key=lambda t: (int(t.get("priority") or 0), str(t.get("title") or "")))


_WARMUP_OPEN = (
    "Give me a quick intro — what have you been working on lately, "
    "and what are you strongest at?"
)
_WARMUP_FOLLOWUPS = (
    "Pick one recent project from that — what did you personally own end to end?",
    "What was the hardest technical decision on that project, and why?",
)

# Follow-ups deepen the last answer; they must not re-ask surface ownership.
_DEEPEN_FOLLOWUPS = (
    "Zoom into one concrete part of what you just described — "
    "what was hard to get right, and how did you work through it?",
    "What tradeoff did you make there, and what evidence convinced you it was the right call?",
)


def stub_question(
    *,
    title: str,
    intent: str | None,
    mode: str,
    followup: bool,
    directive: str | None = None,
    kind: str | None = None,
    followup_index: int = 0,
    prior_user_answer: str | None = None,
) -> str:
    subject = humanize_topic_subject(intent or title)
    if kind == "warmup":
        if directive == "probe":
            return (
                "I want to pin that claim down — what concrete evidence backs it, "
                "and what did you personally do?"
            )
        if directive == "deepen" or followup or mode == "escalate":
            idx = max(0, followup_index - 1) if followup_index > 0 else 0
            return _WARMUP_FOLLOWUPS[min(idx, len(_WARMUP_FOLLOWUPS) - 1)]
        return _WARMUP_OPEN
    if directive == "probe":
        return (
            "I want to pin that down against your resume. "
            "What concrete evidence backs it — the actual numbers, how you measured them, "
            "and what you personally did?"
        )
    if directive == "deepen" or followup or mode == "escalate":
        idx = max(0, followup_index - 1) if followup_index > 0 else 0
        return _DEEPEN_FOLLOWUPS[min(idx, len(_DEEPEN_FOLLOWUPS) - 1)]
    if mode == "direct":
        return (
            f"Looking at {subject} — what's one concrete piece you owned, "
            "and how did you know it worked?"
        )
    # parallel / default
    return (
        f"Let's talk about {subject}. "
        "What have you shipped here, and what was hardest?"
    )
