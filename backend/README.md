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
