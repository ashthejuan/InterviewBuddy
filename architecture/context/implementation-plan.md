# InterviewBuddy — 0→1 Implementation Plan

Status: planning  
Source: `architecture/context/prd.md`  
Last updated: 2026-09-22

---

## Goal

Ship a working voice mock-interview loop: upload resume (+ optional JD) → prep completes → timed grill session → evidence-backed scores → structured debrief.

## Delivery principles

1. **Prep-before-start is a hard gate** — no mid-session embedding races.
2. **Text path first, voice second** — grill + scoring must work over typed turns before LiveKit/Sarvam.
3. **Deterministic assembly > LLM invention** — scoring and reports grounded in chunks/claims/transcript.
4. **Thin vertical slices** — each phase ends with a demoable milestone.
5. **Defer PRD §11 open items** until the slice that needs them (auth last-mile, OCR, PDF reports, deploy target).

## Locked stack (from PRD)

| Layer | Choice |
|-------|--------|
| Frontend | Next.js |
| API | FastAPI |
| Voice | LiveKit Agents |
| STT / TTS | Sarvam Saaras + Bulbul |
| LLM | OpenRouter |
| Embeddings | Local `BAAI/bge-small-en-v1.5` via FastEmbed |
| DB | Postgres + pgvector |
| Files | Cloudflare R2 |
| Packaging | Docker (light images) |

---

## Phase 0 — Scaffold & local platform

**Outcome:** Monorepo boots locally; health checks pass; secrets pattern established.

### Work

- Init `frontend/` (Next.js App Router + TypeScript) and `backend/` (FastAPI + uv/poetry).
- Docker Compose: Postgres 16 + `pgvector`, MinIO or R2-compatible local object store (or R2 sandbox), optional Redis later.
- Shared env template (`.env.example`): DB, R2, OpenRouter, Sarvam, LiveKit keys.
- Backend: `/health`, structured logging, CORS for Next.js.
- Frontend: bare shell + API client stub.
- Alembic (or equivalent) migration runner wired to Postgres.

### Exit criteria

- `docker compose up` → Postgres healthy; FastAPI `/health` 200; Next.js loads.
- Architecture note updated under `architecture/context/`.

### Explicitly out of scope

Auth provider choice (use stub user id until Phase 1).

---

## Phase 1 — Schema, models, session shell

**Outcome:** Full PRD §9 tables exist; can create a session row with settings; statuses enforced.

### Work

- Migrations for: `users`, `documents`, `document_sections`, `document_chunks`, `claims`, `interview_sessions`, `session_topics`, `frontier_nodes`, `turns`, `turn_scores`, `turn_evidence`, `session_results`, `session_reports`.
- `vector(384)` + HNSW index on `document_chunks.embedding`.
- SQLAlchemy/SQLModel (or preferred ORM) models matching schema.
- Session status enum: `preparing | ready | live | completed | failed`.
- Minimal CRUD APIs: create user (dev), create session (settings: duration, difficulty, seniority), get session.

### Exit criteria

- Migration applies cleanly on empty DB.
- Create session → `status=preparing`; GET returns settings + status.

### Notes

- Defer real auth; `users` table + hardcoded/dev user is enough.
- Index plan from PRD §9 implemented in migrations.

---

## Phase 2 — Upload + document prep pipeline

**Outcome:** Resume/JD upload → R2 → extract → section parse → parent–child chunk → embed → claims → lexicon → topics/frontier seed → `status=ready`. Interview start blocked until ready.

### Work

**API / storage**

- Upload endpoints with MIME allowlist + size limits: PDF, TXT, DOCX, MD.
- Store original bytes in R2; metadata on `documents` (`content_type`, `original_filename`, `byte_size`, `parse_status`).

**Extraction**

- PDF: `pypdf` / `pdfminer.six`; fail scanned/image PDFs with clear `parse_status=failed`.
- DOCX: `python-docx`; TXT/MD: encoding-tolerant text read.
- Section-aware parse → `document_sections`.

**Chunking (3+7)**

- Parents = sections/role blocks; children ≈ 50–300 tokens (bullets / requirements).
- Persist `document_chunks` with parent linkage; embed children only via FastEmbed bge-small.

**Claims & lexicon**

- LLM (OpenRouter) or hybrid extract: metrics, ownership, skills, scope → `claims` linked to chunk ids.
- Build `session.lexicon` jsonb (skills, tools, companies, metrics) for later STT repair.

**Topic planning**

- Derive `N_target` from duration (PRD formula).
- Priority: JD must-haves → strong/suspicious claims → behavioral.
- Insert `session_topics` + root `frontier_nodes`; set session `status=ready` (or `failed` on prep error).

**Frontend**

- Upload UI (resume required, JD optional), session settings, prep progress polling, Start disabled until `ready`.

### Exit criteria

- Upload sample resume (+ JD) → session reaches `ready` with chunks, claims, topics, lexicon.
- Start rejected while `preparing` / `failed`.
- Scanned PDF fails gracefully with user-visible error.

### Explicitly deferred

OCR, legacy `.doc`, mid-interview re-embed.

---

## Phase 3 — Grill engine over text (no voice)

**Outcome:** Timed interview works in a chat UI: frontier loop, adaptive question modes, topic exit, wrap.

### Work

**State machine (PRD §8)**

- Topic: `planned → active → scored | skipped`.
- Frontier: `locked → available → in_progress → exhausted | abandoned`.
- Loop: pick topic → unlock roots → ask → receive answer → (score stub OK) → exit criteria → deepen or rotate → wrap.

**Policy**

- Question modes: `parallel | direct | escalate` per situation rules.
- Per-topic soft/hard caps; 1 primary + ≤2 follow-ups default.
- Coverage pressure: rotate when `topics_left > time_left / soft_cap`.
- “I don’t know” valid; dead-end exit.

**Retrieval**

- On each turn: embed query (or use claim text) → pgvector children → expand parents → pack LLM context.

**LLM**

- OpenRouter grill prompts: produce next question + intent metadata; persist `turns` (agent + user).

**Timers**

- Server-authoritative session + topic timers; end on timer or coverage goals.

**Frontend**

- Live session page: transcript, timer, current topic, text answer box, End interview.

### Exit criteria

- Full 10–15 min text session completes through wrap without voice.
- Topics rotate under time pressure; frontier nodes update correctly in DB.

### Notes

- Scoring can be stubbed (fixed or heuristic) if Phase 4 not ready; prefer wiring real scorer ASAP.

---

## Phase 4 — Evidence-backed scoring

**Outcome:** Per-turn rubric → topic rollup → session rollup + hire signal; scores steer frontier.

### Work

- Rubric v1 dims (0–5): Correctness, Relevance, Depth, Structure, Honesty.
- Scorer prompt: transcript turn + retrieved chunks/claims; output scores, confidence, rationale, flags (bluff, contradiction, IDK).
- Persist `turn_scores` + `turn_evidence` (chunk quotes).
- Warmup: light weight.
- Topic rollup → `session_topics`; session rollup → `session_results` (`hire_signal`: needs_work | mixed | solid | strong).
- Grill policy hooks: low depth → deepen; bluff → evidence probe; scorable + time pressure → rotate.
- Deterministic transcript correction module (lexicon → exact → alias → fuzzy ~90–92; no LLM); store `raw_text`, `normalized_text`, `corrections[]`. Grill/score use normalized text.

### Exit criteria

- Completed text session yields dim scores, evidence rows, coverage summary, hire signal.
- Frontier behavior visibly changes based on score flags.

---

## Phase 5 — Voice path (LiveKit + Sarvam)

**Outcome:** Same grill loop over realtime voice; barge-in/turn-taking via LiveKit.

### Work

- LiveKit room creation + token endpoint (FastAPI).
- Python LiveKit **agent worker**: owns normalize → frontier → retrieve → LLM → TTS; writes turns/scores to Postgres.
- Sarvam STT (Saaras streaming; prefer `saaras:v4`; keyterms from session lexicon).
- Sarvam TTS (Bulbul) for agent speech.
- Next.js: join room, mic permissions, mute, connection states; Start only when `ready`.
- Map voice final transcripts through deterministic correction before grill/score.
- Session status `live` while connected; disconnect / End → wrap path.

### Exit criteria

- End-to-end voice interview on a prepared session; transcript + scores persist.
- Barge-in works at LiveKit level; STT keyterms improve rare tech terms on a known resume.

### Deferred

DIY WebRTC, local Whisper/Edge TTS as primary path.

---

## Phase 6 — Post-interview structured report

**Outcome:** After `completed`, candidate sees structured debrief (JSON + markdown); optional PDF later.

### Work

- On session complete → enqueue report job (FastAPI background task / worker).
- Deterministic assembly: scores, coverage map, strengths/gaps, claim-linked notes, JD alignment tables.
- OpenRouter fills fixed JSON schema for prose only (summary, pros/cons, next steps); validate; mark `insufficient_evidence` where unscored.
- Persist `session_reports` (`pending | ready | failed`, `report_json`, `report_markdown`).
- Next.js results page: in-app structured view + markdown download.
- Optional MVP+: markdown → PDF → R2 (`r2_pdf_key`).

### Exit criteria

- Completing a session produces a ready report grounded in DB evidence (no invented topic feedback).
- Results page renders; markdown download works.

---

## Phase 7 — Product hardening & auth

**Outcome:** Usable product boundaries; multi-user safe enough for private beta.

### Work

- Choose and wire auth (Clerk / Supabase Auth / Auth.js — decide in this phase).
- Row-level ownership checks on sessions/documents.
- Error UX: prep failures, voice disconnects, report failures with retry.
- Rate limits on upload + LLM-heavy endpoints.
- Basic observability: request ids, session id in logs, prep/voice/report failure metrics.
- Soft product modes UI if needed (“broad survey” vs “deep dive”) — only if settings already support it.

### Exit criteria

- Another user cannot read your sessions/docs.
- Core failure modes are user-visible and recoverable.

---

## Phase 8 — Docker packaging & deploy

**Outcome:** Reproducible images; deployed staging environment.

### Work

- Multi-service Dockerfiles: Next.js, FastAPI API, LiveKit agent worker, migrations job.
- Keep images light: no PyTorch; FastEmbed/ONNX only; speech via Sarvam APIs.
- Choose deploy target (VPS / Fly / Railway / etc. — open item).
- LiveKit Cloud vs self-host decision documented and implemented.
- Staging smoke test: upload → ready → short voice session → report.

### Exit criteria

- One-command or CI-deployed staging runs the full loop.
- Architecture deploy doc under `architecture/context/`.

---

## Suggested milestone demos

| After phase | Demo |
|-------------|------|
| 0 | Health + empty UI |
| 1 | Session row in DB |
| 2 | Upload resume → ready with chunks/claims |
| 3 | Text grill for 10 minutes |
| 4 | Scores + hire signal on results stub |
| 5 | Voice grill (short session) |
| 6 | Structured debrief page |
| 7 | Signed-in private beta |
| 8 | Staging URL |

---

## Dependency graph (critical path)

```text
Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4
                              ↘         ↗
                               Phase 5 (needs 3; better with 4)
Phase 4 + completed sessions → Phase 6
Phase 5+6 → Phase 7 → Phase 8
```

Phases 4 and 5 can overlap once Phase 3’s state machine is stable: finish scoring on text, then attach the same engine to the agent worker.

---

## Open decisions to resolve by phase

| Open item (PRD §11) | Resolve by |
|---------------------|------------|
| Auth provider | Phase 7 (stub until then) |
| LiveKit Cloud vs self-host | Phase 5 design / Phase 8 deploy |
| Deploy target | Phase 8 |
| OCR / `.doc` | Post-MVP |
| Exact OpenRouter model IDs | Phase 3–4 (grill vs score vs report) |
| Clarify prompts when correction abstains | Phase 4–5 |
| PDF report in MVP | Phase 6 optional; markdown first |

---

## Files expected to grow (target layout)

```text
frontend/          # Next.js app
backend/
  app/             # FastAPI routes, services
  agent/           # LiveKit worker
  migrations/      # Alembic
docker-compose.yml
architecture/context/   # PRD + this plan + per-feature notes
```

Update `architecture/context/` whenever a phase lands (what shipped, how, which files changed).
