# Run from backend/: uv run uvicorn app.main:app --reload --port 8000
# Migrations:     uv run alembic upgrade head
# Tests:          uv run pytest -v   (needs Postgres + MinIO up)
#
# Phase 1 CRUD:
#   POST /users          — create (optionally pass id = DEV_USER_ID)
#   GET  /users/{id}
#   POST /sessions       — status=preparing; user_id defaults to DEV_USER_ID
#   GET  /sessions/{id}
#
# Phase 2 documents:
#   POST /sessions/{id}/documents       — multipart: doc_type + file (pdf/docx/txt/md)
#   POST /sessions/{id}/documents/paste — JSON: {doc_type, text}
#   GET  /documents/{id}                — poll parse_status / raw_text
#   GET  /documents/{id}/sections       — sections + parent/child chunks
#
# Phase 4 scoring (every answer scored before the next question; SCORE_BACKEND=auto|heuristic|openrouter):
#   GET  /sessions/{id}/results         — completed only: overall, hire_signal, strengths/gaps,
#                                          coverage, per-topic rollups, per-turn scores + evidence
#   GET  /sessions/{id}/topics          — now includes rollup_scores
#
# Phase 5 voice (LiveKit + Sarvam):
#   docker compose --profile voice up -d livekit   (or point LIVEKIT_* at LiveKit Cloud)
#   uv run python -m agent.worker download-files   (one-time: Silero VAD model)
#   uv run python -m agent.worker dev              (agent worker; needs SARVAM_API_KEY)
#   GET  /voice/status                  — {enabled} when LIVEKIT_* are set
#   POST /sessions/{id}/voice/token     — live sessions only; room-scoped JWT + agent dispatch
