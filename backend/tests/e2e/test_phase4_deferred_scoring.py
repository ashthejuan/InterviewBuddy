"""E2E: LLM rubric scoring runs after the reply (off the critical path) and always lands
before results are finalized."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.services import scorer
from app.services.scoring import TurnScoreDraft
from tests.e2e.test_phase3_grill import _seed_ready

LLM_RATIONALE = "llm-scored"
BLUFF = "I reduced p99 latency on the billing API by 90% with caching."


def _llm_draft() -> TurnScoreDraft:
    return TurnScoreDraft(
        correctness=3, relevance=3, depth=3, structure=3, honesty=4,
        confidence=0.8, rationale=LLM_RATIONALE,
    )


@pytest.fixture
def gated_llm(monkeypatch: pytest.MonkeyPatch):
    """LLM scorer that blocks until the test opens the gate."""
    gate = threading.Event()
    calls = {"started": 0, "finished": 0}

    async def fake_score_openrouter(**_kw) -> TurnScoreDraft:
        calls["started"] += 1
        await asyncio.to_thread(gate.wait, 10)
        calls["finished"] += 1
        return _llm_draft()

    async def classifier_down(**_kw) -> str | None:
        raise TimeoutError

    monkeypatch.setattr(scorer, "_score_backend", lambda: "openrouter")
    monkeypatch.setattr(scorer, "_score_openrouter", fake_score_openrouter)
    monkeypatch.setattr(scorer, "_classify_openrouter", classifier_down)
    return gate, calls


def _answer(client: TestClient, session_id: str, text: str) -> dict:
    r = client.post(f"/sessions/{session_id}/answer", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def _llm_scored(client: TestClient, session_id: str) -> list[dict]:
    assert client.post(f"/sessions/{session_id}/end").status_code == 200
    res = client.get(f"/sessions/{session_id}/results")
    assert res.status_code == 200, res.text
    return res.json()["turn_scores"]


def test_reply_does_not_wait_for_llm_score(client: TestClient, gated_llm) -> None:
    gate, calls = gated_llm
    session_id = _seed_ready(client, duration=30)
    assert client.post(f"/sessions/{session_id}/start").status_code == 200

    _answer(client, session_id, "I don't know")
    body = _answer(client, session_id, BLUFF)

    # Classifier unavailable → steering falls back to the heuristic signal...
    grill = body["session"]["settings"]["_grill"]
    assert grill["last_score_signal"] == "probe"
    assert grill["last_steer_source"] == "heuristic"
    assert body["agent_turn"] is not None
    # ...while no LLM score has finished yet.
    assert calls["finished"] == 0

    gate.set()
    scores = _llm_scored(client, session_id)
    assert len(scores) == 2
    assert all(s["rationale"] == LLM_RATIONALE for s in scores)


def test_lost_background_scores_are_backfilled_on_end(
    client: TestClient, gated_llm, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate, _ = gated_llm
    gate.set()

    async def dropped(_turn_id) -> None:
        return None

    monkeypatch.setattr(scorer, "run_turn_score_job", dropped)
    session_id = _seed_ready(client, duration=30)
    assert client.post(f"/sessions/{session_id}/start").status_code == 200
    _answer(client, session_id, "I don't know")
    _answer(client, session_id, BLUFF)

    scores = _llm_scored(client, session_id)
    assert len(scores) == 2
    assert all(s["rationale"] == LLM_RATIONALE for s in scores)


SHORT_PRECISE = "Consistent hashing on user_id, 64 shards, rebalanced with virtual nodes."
VAGUE_METRIC = "Pricing lookups got a lot faster after caching, it was a huge win."


def _wait_for_scores(calls: dict, expected: int) -> None:
    deadline = time.time() + 5
    while calls["finished"] < expected and time.time() < deadline:
        time.sleep(0.05)
    time.sleep(0.2)  # let the job commit


def test_classifier_steers_on_content(
    client: TestClient, gated_llm, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate, _ = gated_llm
    gate.set()
    seen: list[str] = []

    async def classifier(*, answer: str, **_kw) -> str | None:
        seen.append(answer)
        return "deepen"

    monkeypatch.setattr(scorer, "_classify_openrouter", classifier)
    session_id = _seed_ready(client, duration=30)
    assert client.post(f"/sessions/{session_id}/start").status_code == 200
    _answer(client, session_id, "I don't know")  # warmup: classifier skipped
    body = _answer(client, session_id, SHORT_PRECISE)

    grill = body["session"]["settings"]["_grill"]
    assert len(seen) == 1 and "64 shards" in seen[0]
    assert grill["last_steer_source"] == "classifier"
    assert grill["last_score_signal"] == "deepen"
    assert grill["last_directive"] == "deepen"


def test_previous_same_topic_llm_bluff_adds_a_probe(
    client: TestClient, gated_llm, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, calls = gated_llm

    async def bluff_score(**_kw) -> TurnScoreDraft:
        calls["finished"] += 1
        draft = _llm_draft()
        draft.flags = {"bluff": True}
        return draft

    async def no_signal(**_kw) -> str | None:
        return None

    monkeypatch.setattr(scorer, "_score_openrouter", bluff_score)
    monkeypatch.setattr(scorer, "_classify_openrouter", no_signal)
    session_id = _seed_ready(client, duration=30)
    assert client.post(f"/sessions/{session_id}/start").status_code == 200
    _answer(client, session_id, "I don't know")
    first = _answer(client, session_id, VAGUE_METRIC)
    topic_id = first["agent_turn"]["topic_id"]
    assert first["session"]["settings"]["_grill"]["last_score_signal"] is None

    _wait_for_scores(calls, expected=2)
    second = _answer(client, session_id, SHORT_PRECISE)
    grill = second["session"]["settings"]["_grill"]
    assert second["agent_turn"]["topic_id"] == topic_id
    assert grill["last_score_signal"] == "probe"
    assert grill["last_directive"] == "probe"
