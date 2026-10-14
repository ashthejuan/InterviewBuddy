"""Unit: content-based steering — LLM classifier (hard cap) + lagged same-topic LLM score."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.config import Settings
from app.models import InterviewSession, SessionTopic
from app.services import scorer
from app.services.grill_policy import merge_lagged_signal

SHORT_PRECISE = "Consistent hashing on user_id, 64 shards, rebalanced with virtual nodes."


# --- merge_lagged_signal -------------------------------------------------------------------


def test_lag_never_overrides_the_current_answer() -> None:
    assert merge_lagged_signal("deepen", "scorable", last_directive=None) == "deepen"
    assert merge_lagged_signal("probe", None, last_directive=None) == "probe"
    assert merge_lagged_signal("scorable", None, last_directive=None) == "scorable"


def test_lag_adds_one_missed_probe() -> None:
    assert merge_lagged_signal(None, "probe", last_directive=None) == "probe"
    assert merge_lagged_signal("deepen", "probe", last_directive="deepen") == "probe"
    assert merge_lagged_signal("scorable", "probe", last_directive=None) == "probe"


def test_lag_does_not_probe_twice() -> None:
    assert merge_lagged_signal(None, "probe", last_directive="probe") is None


def test_lag_lets_a_solid_topic_rotate_on_a_noncommittal_answer() -> None:
    assert merge_lagged_signal(None, "scorable", last_directive=None) == "scorable"
    assert merge_lagged_signal(None, "deepen", last_directive=None) is None


# --- steering_signal -----------------------------------------------------------------------


def _session() -> InterviewSession:
    return InterviewSession(settings={"seniority": "mid"})


def _topic(kind: str = "claim") -> SessionTopic:
    return SessionTopic(title="Sharding the ledger", kind=kind)


def _patch(monkeypatch: pytest.MonkeyPatch, handler) -> list[dict]:
    seen: list[dict] = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return await handler(request)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        scorer.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(_handler), **kw),
    )
    monkeypatch.setattr(
        scorer,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            openrouter_api_key="k",
            default_grill_model="m",
            score_backend="openrouter",
        ),
    )

    async def _no_evidence(*_a, **_kw):
        return []

    monkeypatch.setattr(scorer, "gather_evidence", _no_evidence)
    return seen


def _reply(word: str):
    async def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": word}}]})

    return handler


def _steer(answer: str, kind: str = "claim") -> tuple[str | None, str]:
    return asyncio.run(
        scorer.steering_signal(
            None,  # type: ignore[arg-type]
            _session(),
            _topic(kind),
            intent="sharded the ledger",
            question="How did you shard it?",
            answer=answer,
        )
    )


def test_classifier_judges_content_not_length(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _patch(monkeypatch, _reply("Scorable."))
    assert _steer(SHORT_PRECISE) == ("scorable", "classifier")
    body = seen[0]
    assert body["max_tokens"] <= 10
    assert "length" in body["messages"][0]["content"].lower()
    assert SHORT_PRECISE in body["messages"][1]["content"]


def test_classifier_none_means_no_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _reply("none"))
    assert _steer(SHORT_PRECISE) == (None, "classifier")


def test_unparseable_classifier_output_falls_back_to_heuristic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(monkeypatch, _reply("I think this answer is quite good"))
    assert _steer(SHORT_PRECISE)[1] == "heuristic"


def test_slow_classifier_is_cut_off_at_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow(_r: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1.0)
        return httpx.Response(200, json={"choices": [{"message": {"content": "probe"}}]})

    _patch(monkeypatch, slow)
    monkeypatch.setattr(scorer, "STEER_TIMEOUT_SECONDS", 0.05)
    assert _steer(SHORT_PRECISE)[1] == "heuristic"


def test_warmup_and_idk_skip_the_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _patch(monkeypatch, _reply("probe"))
    assert _steer("I worked on payments mostly.", kind="warmup") == (None, "skip")
    assert _steer("I don't know") == (None, "skip")
    assert seen == []


def test_heuristic_backend_never_calls_the_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _patch(monkeypatch, _reply("probe"))
    monkeypatch.setattr(scorer, "_score_backend", lambda: "heuristic")
    assert _steer(SHORT_PRECISE)[1] == "heuristic"
    assert seen == []
