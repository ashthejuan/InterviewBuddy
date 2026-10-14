"""Unit: SpeechPipe — streamed question text → one TTS utterance."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from agent.controller import SpeechPipe


def test_speech_starts_on_first_chunk_and_ends_on_close() -> None:
    async def run() -> tuple[int, list[str]]:
        streams: list[AsyncIterator[str]] = []
        pipe = SpeechPipe(streams.append)
        pipe.push("")
        assert streams == [] and not pipe.started
        pipe.push("How did ")
        pipe.push("you shard it?")
        pipe.close()
        pipe.close()  # idempotent
        return len(streams), [c async for c in streams[0]]

    count, chunks = asyncio.run(run())
    assert count == 1
    assert chunks == ["How did ", "you shard it?"]


def test_close_without_text_never_starts_speech() -> None:
    streams: list[AsyncIterator[str]] = []
    pipe = SpeechPipe(streams.append)
    pipe.close()
    assert streams == [] and not pipe.started
