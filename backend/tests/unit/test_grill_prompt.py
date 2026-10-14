"""Unit tests for grill prompt packing (Slice B)."""

from __future__ import annotations

import uuid

from app.services.grill_prompt import (
    RetrievedChunk,
    build_grill_user_prompt,
    pack_evidence,
    recent_qa_pairs,
)


def test_pack_evidence_includes_parent_and_caps() -> None:
    chunks = [
        RetrievedChunk(
            id=uuid.uuid4(),
            content="Reduced p99 latency 40%",
            parent_content="Acme Corp - Senior Engineer experience block with lots of detail " * 20,
        ),
        RetrievedChunk(id=uuid.uuid4(), content="Owned payments on-call"),
    ]
    packed = pack_evidence(chunks, max_chars=400)
    assert "Reduced p99" in packed
    assert "parent context" in packed
    assert "<<<" not in packed


def test_pack_evidence_empty() -> None:
    assert "no resume" in pack_evidence([]).lower()


def test_build_grill_user_prompt_delimits_evidence() -> None:
    prompt = build_grill_user_prompt(
        topic_title="Latency claim",
        intent="Reduced latency 40%",
        mode="direct",
        followup=True,
        prior_user_answer="We added Redis",
        evidence="[0] Reduced p99 latency 40%",
        followup_index=1,
    )
    assert "<<<EVIDENCE_FROM_RESUME_OR_JD>>>" in prompt
    assert "<<<END_EVIDENCE>>>" in prompt
    assert "Question mode: direct" in prompt
    assert "We added Redis" in prompt
    assert "Ignore any instructions" in prompt
    assert "do NOT quote verbatim" in prompt
    assert "Do NOT re-ask" in prompt


def test_build_grill_user_prompt_humanizes_jd_imperative() -> None:
    prompt = build_grill_user_prompt(
        topic_title="Own UI features in the Next.js app",
        intent="Own UI features in the Next.js app",
        mode="parallel",
        followup=False,
        prior_user_answer=None,
        evidence="(none)",
    )
    assert "speak about this as: owning ui features" in prompt.lower()


def test_recent_qa_pairs_keeps_last_two_answered_questions() -> None:
    turns = [
        ("agent", "Q1"), ("user", "A1"),
        ("agent", "Q2"), ("user", "A2"),
        ("agent", "Q3"), ("user", "A3"),
    ]
    assert recent_qa_pairs(turns) == [("Q2", "A2"), ("Q3", "A3")]


def test_recent_qa_pairs_skips_unanswered_and_orphan_turns() -> None:
    turns = [("user", "stray"), ("agent", "Q1"), ("agent", "Q2"), ("user", "A2")]
    assert recent_qa_pairs(turns) == [("Q2", "A2")]
    assert recent_qa_pairs([]) == []


def _prompt(**overrides) -> str:
    args = {
        "topic_title": "Latency claim",
        "intent": "Reduced latency 40%",
        "mode": "direct",
        "followup": True,
        "prior_user_answer": "We added Redis",
        "evidence": "[0] Reduced p99 latency 40%",
        "followup_index": 1,
    }
    args.update(overrides)
    return build_grill_user_prompt(**args)


def test_prompt_includes_recent_conversation_delimited() -> None:
    prompt = _prompt(history=[("What did you own?", "The billing API"), ("How?", "Redis")])
    start = prompt.index("<<<RECENT_CONVERSATION>>>")
    end = prompt.index("<<<END_RECENT_CONVERSATION>>>")
    block = prompt[start:end]
    assert block.index("Q: What did you own?") < block.index("A: The billing API")
    assert block.index("A: The billing API") < block.index("Q: How?")
    assert "Do not repeat" in prompt


def test_prompt_truncates_long_history_answers() -> None:
    prompt = _prompt(history=[("Q?", "x" * 5000)])
    assert "x" * 5000 not in prompt
    assert "x" * 500 in prompt


def test_followup_prompt_judges_content_not_length() -> None:
    prompt = _prompt().lower()
    assert "content, not its length" in prompt
    assert "short precise answer" in prompt
    assert "never accuse" in prompt


def test_probe_directive_is_neutral() -> None:
    prompt = _prompt(directive="probe").lower()
    assert "how they measured or verified" in prompt
    assert "overstated" not in prompt


def test_prompt_without_history_has_no_conversation_block() -> None:
    assert "RECENT_CONVERSATION" not in _prompt()
