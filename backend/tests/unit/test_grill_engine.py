"""In-memory grill engine state transitions (Slice A, no LLM)."""

from __future__ import annotations

from app.services.grill_engine import MemNode, MemSession, MemTopic, answer, begin, end


def _session(**kwargs) -> MemSession:
    topics = [
        MemTopic(id="t-warm", title="Warmup intro", kind="warmup", priority=0),
        MemTopic(id="t-claim", title="Reduced latency 40%", kind="claim", priority=50),
        MemTopic(id="t-jd", title="Must have Postgres", kind="jd_must", priority=100),
    ]
    nodes = [
        MemNode(
            id="n-warm",
            topic_id="t-warm",
            intent="Warmup intro",
            question_mode="parallel",
        ),
        MemNode(
            id="n-claim",
            topic_id="t-claim",
            intent="Reduced latency 40%",
            question_mode="direct",
        ),
        MemNode(
            id="n-jd",
            topic_id="t-jd",
            intent="Must have Postgres",
            question_mode="direct",
        ),
    ]
    return MemSession(
        status="live",
        topics=topics,
        nodes=nodes,
        time_left_seconds=kwargs.get("time_left_seconds", 1200),
        soft_cap_default=kwargs.get("soft_cap_default", 210),
    )


def test_begin_activates_warmup_and_asks_first_question() -> None:
    s = _session()
    q = begin(s)
    assert s.topics[0].status == "active"
    assert s.nodes[0].status == "in_progress"
    assert s.nodes[1].status == "locked"
    assert len(s.turns) == 1
    assert s.turns[0].role == "agent"
    assert "warmup" in q.lower() or "experience" in q.lower()


def test_answer_deepens_then_rotates_after_followups() -> None:
    s = _session()
    begin(s)
    q1 = answer(s, "I introduced myself and sketched my background.", seconds_on_topic=30)
    assert q1 is not None
    assert s.nodes[0].followups_used == 1
    assert s.topics[0].status == "active"

    # Burn remaining follow-ups with soft time still OK
    answer(s, "More detail on my role.", seconds_on_topic=60)
    q_last = answer(s, "That covers it.", seconds_on_topic=90)
    assert s.topics[0].status == "scored"
    assert s.nodes[0].status in ("exhausted", "abandoned")
    # Next topic should be highest priority planned (jd_must)
    assert s.topics[2].status == "active"
    assert s.nodes[2].status == "in_progress"
    assert q_last is not None
    assert "postgres" in q_last.lower()


def test_idk_abandons_node_and_rotates() -> None:
    s = _session()
    begin(s)
    q = answer(s, "I don't know", seconds_on_topic=20)
    assert s.topics[0].status == "skipped"
    assert s.nodes[0].status == "abandoned"
    assert s.topics[2].status == "active"  # jd highest priority remaining
    assert q is not None


def test_coverage_pressure_rotates_early() -> None:
    s = _session(time_left_seconds=300)  # 5 min, 2 topics left after current → pressure
    begin(s)
    q = answer(s, "Solid warmup answer with enough content.", seconds_on_topic=60)
    assert s.topics[0].status == "scored"
    assert q is not None
    assert s.topics[2].status == "active"


def test_end_marks_completed_and_skips_remaining() -> None:
    s = _session()
    begin(s)
    end(s, reason="user_ended")
    assert s.status == "completed"
    assert s.wrap_reason == "user_ended"
    assert all(t.status in ("scored", "skipped", "active") for t in s.topics)
    # active should be closed
    assert s.topics[0].status in ("scored", "skipped")
    planned = [t for t in s.topics if t.status == "planned"]
    assert planned == []


def test_session_timer_expiry_wraps() -> None:
    s = _session(time_left_seconds=0)
    begin(s)
    q = answer(s, "Anything", seconds_on_topic=10)
    assert q is None
    assert s.status == "completed"
    assert s.wrap_reason == "timer"
