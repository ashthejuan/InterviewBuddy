"""E2E: Phase 2 upload/paste + extract against Postgres + MinIO."""

from __future__ import annotations

import time
import uuid

from fastapi.testclient import TestClient


def _seed_session(client: TestClient) -> tuple[str, str]:
    user_id = uuid.uuid4()
    client.post(
        "/users",
        json={"id": str(user_id), "email": f"up-{user_id.hex[:10]}@test.local", "name": "Up"},
    )
    session = client.post("/sessions", json={"user_id": str(user_id)}).json()
    return str(user_id), session["id"]


def _wait_doc(client: TestClient, doc_id: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/documents/{doc_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        if body["parse_status"] in ("ready", "failed"):
            return body
        time.sleep(0.1)
    raise AssertionError(f"document {doc_id} did not finish parsing")


def test_upload_txt_extracts_and_links_resume(client: TestClient) -> None:
    _, session_id = _seed_session(client)
    content = b"Jane Doe\nBackend Engineer\nPython, FastAPI\n"
    r = client.post(
        f"/sessions/{session_id}/documents",
        data={"doc_type": "resume"},
        files={"file": ("resume.txt", content, "text/plain")},
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["doc_type"] == "resume"
    assert doc["parse_status"] in ("pending", "processing", "ready")
    assert doc["byte_size"] == len(content)
    assert doc["r2_key"]

    done = _wait_doc(client, doc["id"])
    assert done["parse_status"] == "ready", done
    assert "Jane Doe" in (done["raw_text"] or "")
    assert done["parse_error"] is None

    session = client.get(f"/sessions/{session_id}").json()
    assert session["resume_document_id"] == doc["id"]


def test_paste_jd(client: TestClient) -> None:
    _, session_id = _seed_session(client)
    r = client.post(
        f"/sessions/{session_id}/documents/paste",
        json={"doc_type": "jd", "text": "Must have: Python, Postgres, system design."},
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    done = _wait_doc(client, doc["id"])
    assert done["parse_status"] == "ready"
    assert "Postgres" in done["raw_text"]
    session = client.get(f"/sessions/{session_id}").json()
    assert session["jd_document_id"] == doc["id"]


def test_rejects_oversize_upload(client: TestClient) -> None:
    from app.config import get_settings

    _, session_id = _seed_session(client)
    limit = get_settings().max_upload_bytes
    big = b"%PDF-1.4 " + b"x" * limit
    r = client.post(
        f"/sessions/{session_id}/documents",
        data={"doc_type": "resume"},
        files={"file": ("huge.pdf", big, "application/pdf")},
    )
    assert r.status_code == 413
    assert "too large" in r.json()["detail"].lower()


def test_rejects_bad_extension(client: TestClient) -> None:
    _, session_id = _seed_session(client)
    r = client.post(
        f"/sessions/{session_id}/documents",
        data={"doc_type": "resume"},
        files={"file": ("malware.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    assert r.status_code == 400
