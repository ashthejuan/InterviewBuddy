"""E2E: the grill prompt's recent Q/A history never crosses topics."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services import grill as grill_svc
from tests.e2e.test_phase3_grill import _seed_ready

BLUFF = "I reduced p99 latency on the billing API by 90% with caching."


def test_history_is_scoped_to_the_current_topic(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict] = []
    real_generate = grill_svc.generate_question

    async def recording_generate(*args, **kwargs):
        calls.append(kwargs)
        return await real_generate(*args, **kwargs)

    monkeypatch.setattr(grill_svc, "generate_question", recording_generate)

    session_id = _seed_ready(client, duration=30)
    assert client.post(f"/sessions/{session_id}/start").status_code == 200
    # Warmup "I don't know" → next topic opener; then a bluff → probe follow-up on that topic.
    r = client.post(f"/sessions/{session_id}/answer", json={"text": "I don't know"})
    assert r.status_code == 200, r.text
    core_opener = r.json()["agent_turn"]["raw_text"]
    r = client.post(f"/sessions/{session_id}/answer", json={"text": BLUFF})
    assert r.status_code == 200, r.text

    opener, followup = calls[-2], calls[-1]
    assert opener["followup"] is False
    assert not opener.get("history")
    assert followup["followup"] is True
    assert followup["history"] == [(core_opener, BLUFF)]
