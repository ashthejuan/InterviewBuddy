# InterviewBuddy

You upload a resume and a JD. You run a timed mock interview by text or voice. You read scores tied to transcript quotes and resume chunks.

You prep docs before you start. You grill claims from your own files. You close with a structured report and a PDF download.

## Stack

You click through Next.js pages. You call FastAPI routes. You keep vectors in Postgres with pgvector. You keep files in R2 or MinIO. You call OpenRouter for questions and scores. You speak through LiveKit with Sarvam STT and TTS. You embed docs on your machine with FastEmbed bge-small-en-v1.5.

| Layer | Pick |
| --- | --- |
| UI | Next.js 15, React 19, Tailwind 4 |
| API | FastAPI, SQLAlchemy, Alembic |
| DB | Postgres 16 with pgvector, 384 dims |
| Files | Cloudflare R2, MinIO for dev |
| LLM | OpenRouter, grill plus score. Report prose uses the same key |
| Voice | LiveKit Agents, Sarvam Saaras plus Bulbul |
| Embeddings | FastEmbed, BAAI bge-small-en-v1.5 |

## Prereqs

You need Docker plus uv plus Node 20 plus pnpm or npm.

You need keys for OpenRouter plus Sarvam. You add GitHub OAuth for login. You see no voice button until you set LiveKit vars.

## Run the stack

Copy env and fill secrets:

```bash
cp .env.example .env
# then copy auth vars into frontend
grep -E '^(AUTH_SECRET|AUTH_URL|DATABASE_URL|AUTH_GITHUB_ID|AUTH_GITHUB_SECRET)=' .env > frontend/.env.local
```

Start Postgres plus MinIO:

```bash
docker compose up -d postgres minio
```

Start the API:

```bash
cd backend
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

Start the UI in a second shell:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. Sign up or log in with GitHub. Create a session. Upload a resume and a JD. Wait for status `ready`. Start the interview.

## Session flow

You create a session with duration plus difficulty. You set seniority on the same form. You add resume and JD by file or paste. PDF plus DOCX plus TXT plus MD pass validation at 5 MB max and 100k chars max after extract.

You wait through prep. You get sections split from raw text. You get parent plus child chunks with embeddings in pgvector. You get claims plus topics. You get a lexicon for STT repair. You cannot start until prep marks the session `ready`.

You answer questions live. You get rubric scores for each answer for correctness plus relevance plus depth plus structure plus honesty. You see topic rollups during the run. You end the run when the timer hits zero or when coverage meets the target. You pull JSON plus Markdown from the report job. You download the PDF from the same job.

## API

You send a Bearer JWT from Auth.js on each call. Session rows bind to JWT sub.

```text
POST /users
GET  /users/{id}
POST /sessions
GET  /sessions/{id}
POST /sessions/{id}/start
POST /sessions/{id}/answer
POST /sessions/{id}/end
POST /sessions/{id}/documents
POST /sessions/{id}/documents/paste
GET  /documents/{id}
GET  /documents/{id}/sections
GET  /sessions/{id}/turns
GET  /sessions/{id}/topics
GET  /sessions/{id}/frontier
GET  /sessions/{id}/results
GET  /sessions/{id}/report
GET  /sessions/{id}/report.pdf
POST /sessions/{id}/report/retry
POST /sessions/{id}/export
GET  /voice/status
POST /sessions/{id}/voice/token
```

You hit `GET /health` for a status check.

## Voice path

You join a LiveKit room with a Python agent worker. You run a local server for dev. You point at LiveKit Cloud for prod.

```bash
docker compose --profile voice up -d livekit
cd backend
uv run python -m agent.worker download-files
uv run python -m agent.worker dev
```

Set `LIVEKIT_URL` plus `LIVEKIT_API_KEY` plus `LIVEKIT_API_SECRET` plus `SARVAM_API_KEY`. Request a token from `POST /sessions/{id}/voice/token` after the session turns `live`.

## Layout

```text
backend/
  app/
    main.py
    routers.py
    models.py
    schemas.py
    services/
      prep.py
      grill.py
      scorer.py
      report_job.py
      voice.py
  agent/
    worker.py
  migrations/
  tests/
frontend/
  src/
    app/
      page.tsx
      sessions/
      login/
      signup/
    components/
    lib/
architecture/
  context/
    prd.md
    idea.txt
jd/
resumes/
reports/
interview_logs/
docker-compose.yml
.env.example
```

You run backend tests with Postgres plus MinIO up. You run frontend tests with Vitest.

```bash
cd backend && uv run pytest -v
cd frontend && npm run test
```

Lint backend with Ruff. Lint frontend with ESLint. Typecheck frontend with `npx tsc --noEmit`.

## Config

You set app plus auth plus DB plus R2 plus OpenRouter plus Sarvam plus LiveKit vars in root `.env`. See `.env.example` for defaults. Key switches:

```text
GRILL_BACKEND=auto
SCORE_BACKEND=auto
REPORT_BACKEND=auto
CLAIMS_BACKEND=auto
DEFAULT_GRILL_MODEL=qwen/qwen3.7-flash
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
MAX_UPLOAD_BYTES=5242880
MAX_PASTE_CHARS=100000
```

With `auto`, you call OpenRouter when you set a key and model. You fall back to heuristic rules with low confidence on timeout or key miss. You force `heuristic` or `openrouter` per backend to pin behavior. You use `stub` for offline runs.

## Docs and planning

You find the PRD in `architecture/context/prd.md`. You find the product idea in `architecture/context/idea.txt`. You find phase notes in `architecture/phases/`. You find the backend command map in `backend/README.md`.
