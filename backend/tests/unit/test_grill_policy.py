"""Pure grill policy: exit criteria, IDK, coverage pressure, stub questions."""

from __future__ import annotations

from app.services.grill_policy import (
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
