"""E2E: Phase 4 — evidence-backed scoring steers the frontier and rolls up to results."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.e2e.test_phase3_grill import _seed_ready

DETAILED = (
    "I profiled the billing API first because p99 latency spiked during peak checkout. "
    "Then I added Redis caching for pricing lookups, which meant 40% lower p99 latency, "
    "measured in Grafana over two weeks. The tradeoff was cache invalidation, so I keyed "
    "entries on plan version and owned the on-call runbook for payments."
)


def test_bluff_triggers_probe_and_results_roll_up(client: TestClient) -> None:
    session_id = _seed_ready(client, duration=30)
    assert client.post(f"/sessions/{session_id}/start").status_code == 200
    assert client.get(f"/sessions/{session_id}/results").status_code == 409

    # Skip warmup → first core topic
    r = client.post(f"/sessions/{session_id}/answer", json={"text": "I don't know"})
    assert r.status_code == 200, r.text

    # Overstated metric vs the resume's 40% → bluff flag → evidence probe on the same topic
    before_topic = r.json()["agent_turn"]["topic_id"]
    r = client.post(
        f"/sessions/{session_id}/answer",
        json={"text": "I reduced p99 latency on the billing API by 90% with caching."},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    grill = body["session"]["settings"]["_grill"]
    assert grill["last_score_signal"] == "probe"
    assert grill["last_directive"] == "probe"
    assert body["agent_turn"]["topic_id"] == before_topic
    assert "evidence" in body["agent_turn"]["raw_text"].lower()

    r = client.post(f"/sessions/{session_id}/answer", json={"text": DETAILED})
    assert r.status_code == 200, r.text

    topics = client.get(f"/sessions/{session_id}/topics").json()
    probed = next(t for t in topics if t["id"] == before_topic)
    assert probed["rollup_scores"]["n_turns"] == 2
    assert probed["rollup_scores"]["flags"]["bluff"] == 1

    assert client.post(f"/sessions/{session_id}/end").status_code == 200

    res = client.get(f"/sessions/{session_id}/results")
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["hire_signal"] in ("needs_work", "mixed", "solid", "strong")
    assert out["overall_score"] is not None
    assert len(out["turn_scores"]) == 3
    for ts in out["turn_scores"]:
        for dim in ("correctness", "relevance", "depth", "structure", "honesty"):
            assert 0 <= ts[dim] <= 5
    bluffed = [ts for ts in out["turn_scores"] if ts["flags"].get("bluff")]
    assert len(bluffed) == 1
    assert bluffed[0]["evidence"], "bluff score must cite resume evidence"
    assert bluffed[0]["evidence"][0]["source"] == "resume"
    assert "40%" in " ".join(e["quote"] for e in bluffed[0]["evidence"])
    assert out["turn_scores"][0]["flags"] == {"idk": True}

    counts = out["coverage_summary"]["counts"]
    assert sum(counts.values()) == len(topics)
    assert counts["skipped"] >= 1
    assert any(g["topic_id"] == before_topic for g in out["gaps"])
    assert set(out["coverage_summary"]["dims"]) == {
        "correctness", "relevance", "depth", "structure", "honesty"
    }

    # Reads are stable (no duplicate result rows)
    again = client.get(f"/sessions/{session_id}/results").json()
    assert again["overall_score"] == out["overall_score"]


def test_ending_without_answers_yields_empty_but_valid_results(client: TestClient) -> None:
    session_id = _seed_ready(client)
    client.post(f"/sessions/{session_id}/start")
    client.post(f"/sessions/{session_id}/end")
    out = client.get(f"/sessions/{session_id}/results").json()
    assert out["overall_score"] is None
    assert out["hire_signal"] is None
    assert out["turn_scores"] == []
    assert out["coverage_summary"]["counts"]["skipped"] >= 1
