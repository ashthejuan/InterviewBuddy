"""In-memory grill engine — Slice A state machine (stub questions, no LLM)."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.grill_policy import (
    looks_like_idk,
    pick_next_topic,
    should_exit_topic,
    stub_question,
)


@dataclass
class MemTurn:
    role: str
    text: str
    topic_id: str | None = None
    node_id: str | None = None


@dataclass
class MemTopic:
    id: str
    title: str
    kind: str
    priority: int
    status: str = "planned"
    soft_cap_seconds: int = 210
    hard_cap_seconds: int = 330
    seconds_spent: int = 0


@dataclass
class MemNode:
    id: str
    topic_id: str
    intent: str
    question_mode: str
    status: str = "locked"
    max_followups: int = 2
    followups_used: int = 0


@dataclass
class MemSession:
    status: str
    topics: list[MemTopic]
    nodes: list[MemNode]
    time_left_seconds: int
    soft_cap_default: int = 210
    turns: list[MemTurn] = field(default_factory=list)
    wrap_reason: str | None = None
    active_topic_id: str | None = None
    active_node_id: str | None = None


def begin(session: MemSession) -> str:
    topic = _activate_next(session)
    if topic is None:
        session.status = "completed"
        session.wrap_reason = "no_topics"
        return "We're done — no topics were planned."
    node = _active_node(session)
    assert node is not None
    q = stub_question(
        title=topic.title,
        intent=node.intent,
        mode=node.question_mode,
        followup=False,
    )
    session.turns.append(
        MemTurn(role="agent", text=q, topic_id=topic.id, node_id=node.id)
    )
    return q


def answer(session: MemSession, text: str, *, seconds_on_topic: int) -> str | None:
    if session.status != "live":
        return None
    if session.time_left_seconds <= 0:
        _wrap(session, "timer")
        return None

    topic = _topic_by_id(session, session.active_topic_id)
    node = _active_node(session)
    if topic is None or node is None:
        _wrap(session, "no_topics")
        return None

    topic.seconds_spent = seconds_on_topic
    session.turns.append(
        MemTurn(role="user", text=text, topic_id=topic.id, node_id=node.id)
    )

    idk = looks_like_idk(text)
    topics_left = len(
        [t for t in session.topics if t.status == "planned" and t.id != topic.id]
    )
    exit_, reason = should_exit_topic(
        seconds_spent=topic.seconds_spent,
        soft_cap=topic.soft_cap_seconds,
        hard_cap=topic.hard_cap_seconds,
        followups_used=node.followups_used,
        max_followups=node.max_followups,
        answer_is_idk=idk,
        topics_left=topics_left,
        time_left_seconds=session.time_left_seconds,
    )

    if not exit_:
        node.followups_used += 1
        q = stub_question(
            title=topic.title,
            intent=node.intent,
            mode="escalate" if node.followups_used > 1 else node.question_mode,
            followup=True,
        )
        session.turns.append(
            MemTurn(role="agent", text=q, topic_id=topic.id, node_id=node.id)
        )
        return q

    _close_topic(topic, node, reason=reason)
    session.active_topic_id = None
    session.active_node_id = None

    nxt = _activate_next(session)
    if nxt is None:
        _wrap(session, "coverage")
        return None

    nxt_node = _active_node(session)
    assert nxt_node is not None
    q = stub_question(
        title=nxt.title,
        intent=nxt_node.intent,
        mode=nxt_node.question_mode,
        followup=False,
    )
    session.turns.append(
        MemTurn(role="agent", text=q, topic_id=nxt.id, node_id=nxt_node.id)
    )
    return q


def end(session: MemSession, reason: str = "user_ended") -> None:
    _wrap(session, reason)


def _wrap(session: MemSession, reason: str) -> None:
    if session.active_topic_id:
        topic = _topic_by_id(session, session.active_topic_id)
        node = _active_node(session)
        if topic and node:
            _close_topic(topic, node, reason="user_ended" if reason == "user_ended" else "wrap")
    for t in session.topics:
        if t.status == "planned":
            t.status = "skipped"
        elif t.status == "active":
            t.status = "skipped"
    for n in session.nodes:
        if n.status in ("available", "in_progress", "locked"):
            if n.status == "locked":
                continue  # leave locked on skipped topics? mark abandoned for active paths
            n.status = "abandoned"
    # Skip remaining locked nodes on skipped topics
    for t in session.topics:
        if t.status == "skipped":
            for n in session.nodes:
                if n.topic_id == t.id and n.status == "locked":
                    n.status = "abandoned"
    session.active_topic_id = None
    session.active_node_id = None
    session.status = "completed"
    session.wrap_reason = reason


def _close_topic(topic: MemTopic, node: MemNode, *, reason: str) -> None:
    if reason == "idk":
        topic.status = "skipped"
        node.status = "abandoned"
    else:
        topic.status = "scored"
        node.status = "exhausted"


def _activate_next(session: MemSession) -> MemTopic | None:
    payload = [
        {
            "id": t.id,
            "kind": t.kind,
            "priority": t.priority,
            "status": t.status,
            "title": t.title,
        }
        for t in session.topics
    ]
    picked = pick_next_topic(payload)
    if picked is None:
        return None
    topic = _topic_by_id(session, picked["id"])
    assert topic is not None
    topic.status = "active"
    roots = [
        n
        for n in session.nodes
        if n.topic_id == topic.id and n.status == "locked"
    ]
    if not roots:
        roots = [n for n in session.nodes if n.topic_id == topic.id]
    node = roots[0]
    node.status = "in_progress"
    session.active_topic_id = topic.id
    session.active_node_id = node.id
    return topic


def _topic_by_id(session: MemSession, topic_id: str | None) -> MemTopic | None:
    if topic_id is None:
        return None
    for t in session.topics:
        if t.id == topic_id:
            return t
    return None


def _active_node(session: MemSession) -> MemNode | None:
    if session.active_node_id is None:
        return None
    for n in session.nodes:
        if n.id == session.active_node_id:
            return n
    return None
