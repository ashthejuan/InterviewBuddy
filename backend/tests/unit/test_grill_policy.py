"""Pure grill policy: exit criteria, IDK, coverage pressure, stub questions."""

from __future__ import annotations

from app.services.grill_policy import (
    apply_score_signal,
    looks_like_idk,
    pick_next_topic,
    should_exit_topic,
    stub_question,
)


def test_looks_like_idk_detects_common_phrases() -> None:
    assert looks_like_idk("I don't know")
    assert looks_like_idk("idk, honestly")
    assert looks_like_idk("I'm not sure about that")
    assert looks_like_idk("No idea")
    assert not looks_like_idk("I led the migration to Postgres")


def test_should_exit_on_hard_cap() -> None:
    exit_, reason = should_exit_topic(
        seconds_spent=330,
        soft_cap=210,
        hard_cap=330,
        followups_used=0,
        max_followups=2,
        answer_is_idk=False,
        topics_left=2,
        time_left_seconds=600,
    )
    assert exit_ is True
    assert reason == "hard_cap"


def test_should_exit_on_idk() -> None:
    exit_, reason = should_exit_topic(
        seconds_spent=30,
        soft_cap=210,
        hard_cap=330,
        followups_used=0,
        max_followups=2,
        answer_is_idk=True,
        topics_left=2,
        time_left_seconds=600,
    )
    assert exit_ is True
    assert reason == "idk"


def test_should_exit_when_followups_exhausted() -> None:
    exit_, reason = should_exit_topic(
        seconds_spent=60,
        soft_cap=210,
        hard_cap=330,
        followups_used=2,
        max_followups=2,
        answer_is_idk=False,
        topics_left=2,
        time_left_seconds=600,
    )
    assert exit_ is True
    assert reason == "followups_exhausted"


def test_should_exit_on_coverage_pressure() -> None:
    # 3 topics left, 5 min left, soft 3.5 min → pressure
    exit_, reason = should_exit_topic(
        seconds_spent=60,
        soft_cap=210,
        hard_cap=330,
        followups_used=0,
        max_followups=2,
        answer_is_idk=False,
        topics_left=3,
        time_left_seconds=300,
    )
    assert exit_ is True
    assert reason == "coverage_pressure"


def test_should_not_exit_early_when_time_comfortable() -> None:
    exit_, reason = should_exit_topic(
        seconds_spent=60,
        soft_cap=210,
        hard_cap=330,
        followups_used=0,
        max_followups=2,
        answer_is_idk=False,
        topics_left=2,
        time_left_seconds=900,
    )
    assert exit_ is False
    assert reason == ""


def test_soft_cap_exits_when_no_coverage_pressure() -> None:
    exit_, reason = should_exit_topic(
        seconds_spent=210,
        soft_cap=210,
        hard_cap=330,
        followups_used=0,
        max_followups=2,
        answer_is_idk=False,
        topics_left=1,
        time_left_seconds=900,
    )
    assert exit_ is True
    assert reason == "soft_cap"


def test_pick_next_topic_prefers_warmup_then_priority() -> None:
    topics = [
        {"id": "a", "kind": "claim", "priority": 50, "status": "planned", "title": "Latency"},
        {"id": "b", "kind": "warmup", "priority": 0, "status": "planned", "title": "Warmup"},
        {"id": "c", "kind": "jd_must", "priority": 100, "status": "planned", "title": "Postgres"},
        {"id": "d", "kind": "claim", "priority": 80, "status": "scored", "title": "Done"},
    ]
    nxt = pick_next_topic(topics)
    assert nxt is not None
    assert nxt["id"] == "b"

    topics[1]["status"] = "scored"
    nxt = pick_next_topic(topics)
    assert nxt is not None
    assert nxt["id"] == "c"


def test_stub_question_varies_by_mode() -> None:
    parallel = stub_question(
        title="Warmup intro", intent="Warmup intro", mode="parallel", followup=False
    )
    direct = stub_question(
        title="Reduced latency 40%",
        intent="Reduced latency 40%",
        mode="direct",
        followup=False,
    )
    escalate = stub_question(
        title="Postgres", intent="Must have Postgres", mode="escalate", followup=True
    )
    assert "experience" in parallel.lower() or "tell me" in parallel.lower()
    assert "reduced latency" in direct.lower()
    assert "example" in escalate.lower() or "concrete" in escalate.lower()
    assert parallel != direct


def _apply(exit_: bool, reason: str, signal: str | None, **kw):
    args = {
        "seconds_spent": 60, "soft_cap": 210, "followups_used": 0, "max_followups": 2,
        "topics_left": 2, "time_left_seconds": 900,
    }
    args.update(kw)
    return apply_score_signal(exit_, reason, signal=signal, **args)


def test_score_signal_never_overrides_idk_or_hard_cap() -> None:
    assert _apply(True, "idk", "probe") == (True, "idk", None)
    assert _apply(True, "hard_cap", "deepen") == (True, "hard_cap", None)


def test_probe_grants_one_extra_followup() -> None:
    assert _apply(True, "followups_exhausted", "probe", followups_used=2) == (False, "", "probe")
    assert _apply(True, "coverage_pressure", "probe") == (False, "", "probe")
    # Budget + 1 already used → probing stops
    assert _apply(True, "followups_exhausted", "probe", followups_used=3)[0] is True


def test_deepen_respects_breadth_and_soft_time() -> None:
    assert _apply(False, "", "deepen") == (False, "", "deepen")
    assert _apply(True, "followups_exhausted", "deepen", followups_used=2) == (False, "", "deepen")
    assert _apply(True, "followups_exhausted", "deepen", followups_used=2, seconds_spent=220)[0]
    assert _apply(True, "coverage_pressure", "deepen") == (True, "coverage_pressure", None)


def test_scorable_rotates_only_under_time_pressure() -> None:
    assert _apply(False, "", "scorable") == (False, "", None)
    assert _apply(False, "", "scorable", seconds_spent=110) == (True, "scorable", None)
    assert _apply(False, "", "scorable", topics_left=3, time_left_seconds=800) == (
        True, "scorable", None
    )
    assert _apply(False, "", "scorable", seconds_spent=110, topics_left=0)[0] is False


def test_stub_question_directives() -> None:
    probe = stub_question(title="t", intent="Reduced latency 40%", mode="direct",
                          followup=True, directive="probe")
    deepen = stub_question(title="t", intent="Postgres", mode="direct",
                           followup=True, directive="deepen")
    assert "evidence" in probe.lower()
    assert "deeper" in deepen.lower()
