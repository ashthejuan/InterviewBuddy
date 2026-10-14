"""Tests for grill question cleanup helpers + streamed generation."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.config import Settings
from app.services import grill_questions as gq
from app.services.grill_questions import QuestionStreamCleaner, _clean_question


def test_clean_question_strips_label_and_quotes() -> None:
    assert _clean_question('Question: "What did you own?"') == "What did you own?"
    assert _clean_question("Q - Tell me more.\n\nExtra paragraph") == "Tell me more."


def _stream_through(cleaner: QuestionStreamCleaner, raw: str, step: int = 3) -> str:
    out = "".join(cleaner.feed(raw[i : i + step]) for i in range(0, len(raw), step))
    return out + cleaner.finish()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('Question: "What did you own?"', "What did you own?"),
        ("Q - Tell me more.\n\nExtra paragraph", "Tell me more."),
        ("How did you measure the p95 drop? Walk me through it.", "How did you measure the p95 drop? Walk me through it."),
        ("Quick one: why Redis?", "Quick one: why Redis?"),
    ],
)
def test_stream_cleaner_speaks_what_it_stores(raw: str, expected: str) -> None:
    cleaner = QuestionStreamCleaner()
    spoken = _stream_through(cleaner, raw)
    assert spoken.strip() == expected
    assert cleaner.text == expected


class _Sink:
    def __init__(self) -> None:
        self.chunks: list[str] = []
        self.closed = False

    def push(self, text: str) -> None:
        self.chunks.append(text)

    def close(self) -> None:
        self.closed = True


def _sse(*deltas: str, error_after: bool = False) -> bytes:
    lines = [": OPENROUTER PROCESSING", ""]
    for d in deltas:
        lines += ["data: " + json.dumps({"choices": [{"delta": {"content": d}}]}), ""]
    if error_after:
        lines += ["data: " + json.dumps({"error": {"message": "provider died"}}), ""]
    else:
        lines += ["data: [DONE]", ""]
    return "\n".join(lines).encode()


def _patch_openrouter(monkeypatch: pytest.MonkeyPatch, handler) -> list[dict]:
    seen: list[dict] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return handler(request)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        gq.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(_handler), **kw),
    )
    monkeypatch.setattr(
        gq,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            openrouter_api_key="k",
            default_grill_model="m",
            grill_backend="openrouter",
        ),
    )

    async def _no_chunks(*_a, **_kw):
        return []

    monkeypatch.setattr(gq, "retrieve_for_session", _no_chunks)
    return seen


def _generate(sink: _Sink | None, history: list[tuple[str, str]] | None = None) -> str:
    return asyncio.run(
        gq.generate_question(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            title="Billing API",
            intent="owned the billing API",
            mode="direct",
            followup=False,
            sink=sink,
            history=history,
        )
    )


def test_recent_conversation_reaches_the_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _patch_openrouter(
        monkeypatch,
        lambda _r: httpx.Response(200, json={"choices": [{"message": {"content": "Why?"}}]}),
    )
    _generate(None, history=[("What did you own?", "The ledger service")])
    user_msg = seen[0]["messages"][1]["content"]
    assert "Q: What did you own?" in user_msg
    assert "A: The ledger service" in user_msg


def test_streamed_question_reaches_sink_and_is_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _patch_openrouter(
        monkeypatch,
        lambda _r: httpx.Response(200, content=_sse("Question: ", "How did you ", "shard it?")),
    )
    sink = _Sink()
    text = _generate(sink)
    assert seen[0]["stream"] is True
    assert text == "How did you shard it?"
    assert "".join(sink.chunks).strip() == text
    assert sink.closed


def test_stream_failure_before_text_falls_back_to_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_openrouter(monkeypatch, lambda _r: httpx.Response(503, content=b"down"))
    sink = _Sink()
    text = _generate(sink)
    assert text  # stub question
    assert sink.chunks == []
    assert sink.closed


def test_stream_failure_mid_question_keeps_what_was_spoken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_openrouter(
        monkeypatch,
        lambda _r: httpx.Response(
            200, content=_sse("Walk me through how you sharded the ledger tables.", error_after=True)
        ),
    )
    sink = _Sink()
    text = _generate(sink)
    assert text == "Walk me through how you sharded the ledger tables."
    assert "".join(sink.chunks).strip() == text


def test_without_sink_question_is_not_streamed(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _patch_openrouter(
        monkeypatch,
        lambda _r: httpx.Response(
            200, json={"choices": [{"message": {"content": "Why Postgres?"}}]}
        ),
    )
    assert _generate(None) == "Why Postgres?"
    assert "stream" not in seen[0]
