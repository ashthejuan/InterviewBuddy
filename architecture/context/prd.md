# InterviewBuddy — Product & Technical Decisions (PRD)

Status: brainstorming decisions locked for implementation planning  
Last updated: 2026-09-24

---

## 1. Product summary

Interactive **voice** mock-interview application. The candidate uploads a **resume** and optional **JD**; the system prepares document context **before** the interview starts, then runs a timed, breadth-aware grill session. Questions are driven by a **grill-me–style** inquiry engine. Answers are scored with an evidence-backed rubric grounded in resume/JD retrieval.

### Core value

Document-conditioned grilling (not generic question banks): vet the candidate’s own claims and JD alignment under time pressure.

---



## 2. Stack decisions


| Layer                            | Choice                                       | Notes                                                             |
| -------------------------------- | -------------------------------------------- | ----------------------------------------------------------------- |
| Frontend                         | **Next.js**                                  |                                                                   |
| API / backend                    | **Python + FastAPI**                         |                                                                   |
| Voice transport / agent plumbing | **LiveKit** (Agents)                         | Rooms, turn-taking, barge-in; not reinventing WebRTC              |
| STT                              | **Sarvam Saaras** (streaming / realtime API) | Prefer `saaras:v4` when available; `en-IN` or auto                |
| TTS                              | **Sarvam Bulbul** (API)                      | Same vendor as STT                                                |
| LLM                              | **OpenRouter**                               | Grill logic, scoring prompts; pick low-latency models for turns   |
| Embeddings                       | **Local** `BAAI/bge-small-en-v1.5`           | Via **FastEmbed / ONNX** (no heavy PyTorch if avoidable)          |
| Vector + primary DB              | **Postgres + pgvector**                      | `vector(384)`, cosine / HNSW                                      |
| File storage                     | **Cloudflare R2**                            | Original resume/JD files; extracted text lives in Postgres        |
| Packaging                        | **Docker**, keep images lightweight          | Embeddings local; speech I/O via Sarvam to avoid STT/TTS sidecars |
| Live session state               | In-memory / optional Redis                   | Persist topic/frontier summaries and turns to Postgres            |




### Explicitly deferred / rejected


| Item                                                | Decision                                                        |
| --------------------------------------------------- | --------------------------------------------------------------- |
| Embed mid-interview during warmup                   | **Rejected** — prep must finish before Start                    |
| DIY WebRTC + local Whisper/Edge TTS as primary path | **Deferred** — LiveKit + Sarvam preferred                       |
| Chroma / Pinecone / Mongo vector search             | **Rejected for MVP** — Postgres + pgvector                      |
| arctic-embed-xs / arctic-embed-s                    | **Deferred** — bge-small locked; same 384 dims if swapped later |
| Embedding SaaS (OpenAI/Voyage, etc.)                | **Avoid for MVP**                                               |
| LLM-based ASR term correction                       | **Rejected** — deterministic correction only                    |
| Semantic chunking as primary strategy               | **Rejected** for resume/JD corpus                               |


---



## 3. Document prep pipeline

### 3.1 Supported upload formats (locked)

Resume and JD may be uploaded as **files** or **pasted text**:

| Format | Extensions / input | Extract approach (FastAPI) |
|--------|--------------------|----------------------------|
| PDF | `.pdf` | `pypdf` / `pdfminer.six` for text PDFs; flag scanned/image PDFs for OCR later |
| Plain text | `.txt` | UTF-8 read (fallback encodings) |
| Word | `.docx` | `python-docx` (MVP: `.docx` only, not legacy `.doc`) |
| Markdown | `.md` / `.markdown` | Read as text; preserve headings for section hints |
| Paste | JSON/text body (no file) | Same path as TXT after length check; optional store as `.txt` in R2 for audit |

- Store **original bytes in R2** (files; paste may be stored as `.txt`); store `content_type`, `original_filename`, `byte_size` on `documents`.
- Extraction / validation failure → `parse_status = failed` with user-visible error (e.g. scanned PDF needs OCR — deferred; too large; parse timeout).

### 3.1.1 Upload & extraction safety (locked)

Treat all uploads and pasted text as **untrusted data**. Validation is O(n) in file/text size and **must not** add a second model call.

**Crash / DoS (enforce earliest first)**

| Control | Rule | On violate |
|---------|------|------------|
| Hard request size | Max upload **5 MB** (`Content-Length` + actual bytes read). Prefer stream to R2; do not keep full bytes in the API process longer than needed. | `413` / `400` before R2 / prep |
| Allowlist + sniff | Allow only PDF, DOCX, TXT, MD (+ paste). Verify extension **and** magic bytes / DOCX zip header; reject Content-Type or filename mismatch. | `400` |
| Paste / input cap | Pasted body max **100k characters** (same budget as post-extract text). | `400` |
| Post-extract caps | After extract: max **100k chars** of plain text; PDF max **30 pages**; DOCX max **uncompressed** size (e.g. **20 MB** expanded) to blunt zip bombs. Exceed → fail (or truncate only if product later opts in; MVP = **fail**). | `parse_status=failed` |
| Extract timeout | Wall-clock cap on PDF/DOCX extract (e.g. **10 s**). Timeout ≠ “too large” — it means unsuitable/pathological to parse; same user-facing failure family as scan/OCR-needed. | `parse_status=failed` |
| Async prep | Upload/paste returns after R2 + `documents` row (`parse_status=pending`/`processing`). Chunk/embed/claims/topics run off the request path with worker timeouts. | N/A (UX) |

Structural caps (bytes/pages/chars/uncompressed) are the “too large / too dense” signal. Timeouts are a **backstop** for misbehaving content.

**Prompt injection (document content has no instruction authority)**

| Control | Rule |
|---------|------|
| Role separation | Fixed system/policy prompts. Resume/JD only in delimited **data** blocks (or retrieved evidence quotes) — never concatenated into the system prompt. |
| Normalize text | After extract: Unicode NFC, strip nulls/control chars; store `raw_text` for audit; feed **normalized** text to chunk/embed/LLM. |
| Retrieval packing | Grill/score context packs chunks as candidate-provided **evidence**, with an explicit instruction to ignore directives inside documents. |
| No execution surface | PDF/DOCX → plain text only. Never eval, shell, or HTML-render uploaded bytes. |

Deferred (not MVP): jailbreak-phrase classifiers, per-user rate limits (Phase 7).

### 3.2 Prep steps

1. User uploads resume (+ optional JD) or pastes text → validate (§3.1.1) → store in **R2**; metadata in Postgres; return quickly while prep continues async.
2. Format-specific extract (bounded) → normalize → plain text → **section-aware parse**.
3. Chunk with **parent–child** strategy (see §4).
4. Embed children with **bge-small** → store in **pgvector**.
5. Extract **claims** (metrics, ownership, skills, scope) linked to chunk ids — LLM sees documents only as delimited data (§3.1.1).
6. Build **session lexicon** (skills, tools, companies, metrics) for STT keyterms + deterministic repair.
7. Plan **topics** + initial **frontier nodes**; set session `status = ready`.
8. Interview **must not start** until prep is ready (no async embed race mid-conversation).

---



## 3A. Post-interview structured report (locked)

After the session ends, generate a **structured debrief document** the candidate can read/download. It is grounded in **session scores + transcript + resume/JD claims/chunks** (not a free-form essay from memory).

### 3A.1 Report contents

| Section | Source |
|---------|--------|
| Session meta | duration, difficulty, seniority, docs used |
| Overall signal | hire_signal, overall score, short summary |
| Coverage map | topics grilled / light / skipped vs planned N |
| Topic-by-topic notes | each `session_topic`: what was asked (intents), how they did, dim scores |
| Strengths | top strong turns + linked resume claims/chunks |
| Weaknesses / gaps | low scores, contradictions, bluff flags, JD gaps |
| Pros / cons | synthesized from strengths vs gaps (structured bullets) |
| Resume-linked notes | per discussed claim: “resume said X → interview showed Y” |
| JD alignment (if JD) | requirements covered / weak / missing |
| Actionable next steps | 3–5 concrete practice items |
| Appendix (optional) | key quotes, correction log highlights |

### 3A.2 Implementation flow

```text
session.status → completed
  → enqueue report job (FastAPI background task / worker)
  → assemble structured context from Postgres:
       session_topics, turns, turn_scores, turn_evidence,
       claims, chunks (parent text), session_results partials
  → OpenRouter: fill a fixed JSON report schema (one shot or map-reduce by topic)
  → validate schema
  → persist session_reports (json + rendered markdown)
  → optional: render PDF → R2 (download link in Next.js)
```

**Do not** regenerate the whole interview from scratch. Prefer:

1. **Deterministic assembly** of tables (scores, coverage, evidence quotes).  
2. **LLM polish** only for prose sections (summary, pros/cons, next steps) constrained to that assembled evidence.  
3. If a topic has no scores, mark `insufficient_evidence` — don’t invent feedback.

### 3A.3 Storage

- **`session_reports`**: `session_id`, `status` (`pending`|`ready`|`failed`), `report_json` jsonb, `report_markdown` text, `r2_pdf_key` nullable, timestamps.  
- Extend **`session_results`** or replace debrief fields with FK to `session_reports`.  
- Next.js: results page renders markdown/JSON; “Download PDF” if rendered.

### 3A.4 Formats delivered to user

- In-app structured view (primary)  
- Markdown download  
- PDF download (optional MVP+: markdown → PDF via WeasyPrint/Puppeteer-equivalent)

---



## 4. Chunking strategy (locked): 3 + 7

**Section-aware parse (3) + parent–child retrieval (7).**


| Level  | What                                                                 | Role                              |
| ------ | -------------------------------------------------------------------- | --------------------------------- |
| Parent | Section or role block (Experience entry, Projects block, JD section) | Rich context for LLM prompts      |
| Child  | Bullet, short role summary, or JD requirement                        | Embedded + retrieved via pgvector |


- Child size target: ~50–300 tokens; merge tiny orphans.  
- Resume children ≈ bullets/roles; JD children ≈ requirements.  
- Claims point at child chunk ids.  
- Retrieve children; expand to parent when building grill/score context.

---



## 5. Interview engine (grill-me adaptation)

Inspired by [/grill-me](https://www.aihero.dev/skills-grill-me): rounds, **frontier**, prerequisite gating, “I don’t know” is valid.

### Adaptations for interviews

- Frontier seeded from **resume claims + JD must-haves** (+ warmup/behavioral).  
- Session is **stateful** (transcript, scores, retrieval, timers) — not stateless like the original skill.  
- End when **timer** or coverage goals met (not only “frontier empty”).  
- Scoring feeds frontier: deepen vs rotate.



### Question style (adaptive — not always parallel)


| Situation                              | Behavior                                                         |
| -------------------------------------- | ---------------------------------------------------------------- |
| Soft / easy to lead the witness        | Prefer **parallel/generic** question; score against latent claim |
| Concrete, measurable, defensible claim | Ask **direct** claim probes                                      |
| Vague answer on a measurable claim     | Escalate: generic → tighten → resume-grounded                    |




### Time & coverage (example: 30-minute session)


| Phase              | Approx   | Goal                                           |
| ------------------ | -------- | ---------------------------------------------- |
| Warmup             | ~3 min   | Light / low-weight score                       |
| Core topics        | ~22 min  | Hit **N** topics with enough evidence to score |
| Buffer / deep dive | ~3–5 min | Only if breadth on pace                        |
| Wrap               | ~2 min   | Clean close                                    |


**N topics:** derived, not fixed.

```text
N_max ≈ floor(T_core / soft_cap)     # e.g. 22 / 3.5 ≈ 6
N_min ≈ max(3, ceil(0.5 * N_max))
N_target = clamp(count(priority_topics), N_min, N_max)
```

Priority order: JD must-haves → strong/suspicious claims → behavioral → nice-to-haves if time remains.

### Per-topic caps

- Soft ~3–4 min; hard ~5–6 min then forced switch.  
- Default: 1 primary question + ≤2 follow-ups (≤3 on hard if time allows).



### Topic exit criteria (“enough”)

Close topic/branch when any apply:

- **Scorable** (rubric dims fillable with evidence)
- **Diminishing returns** on follow-ups
- Soft/hard time hit
- Dead end (“I don’t know” with no useful recovery)
- Contradiction resolved
- **Coverage pressure** (`topics_left > time_left / soft_cap`)

Depth allowed only if JD-critical, breadth on pace, soft time not hit, and last answer was promising but shallow.

---



## 6. Scoring rubric



### Principles

- Evidence-backed (transcript + retrieved chunks)  
- Per-answer → topic rollup → session rollup  
- Separate content from delivery  
- Difficulty- and seniority-aware  
- Honest “I don’t know” ≠ auto-fail; bluffing penalized more than gaps



### v1 dimensions (0–5)

Correctness, Relevance, Depth, Structure, Honesty  

Later optional: Specificity, Delivery (keep delivery ≤ ~10–15% of rollup unless presence mode).

### Scale

0 missing → 3 meets bar for selected seniority → 5 exceptional for that level.

### Warmup

Light score / low weight so early nerves don’t dominate.

### Session output

- Weighted rollup (core grill > behavioral > warmup)  
- Hire signal (practice framing): `needs_work | mixed | solid | strong`  
- Top strengths/gaps, JD coverage (grilled / light / skipped)  
- Consistency checks across turns



### Grill ↔ scores

Rubric output helps grow/prune frontier (e.g. low depth → one deepen; bluff flag → evidence probe; scorable + time pressure → rotate).

---



## 7. Speech pipeline



### Sarvam

- **TTS:** Bulbul  
- **STT:** Saaras streaming/realtime; inject **session lexicon** as **keyterms** for tech terms, names, metrics  
- Cost order-of-magnitude: STT ~₹30/hour audio; TTS ~₹30/10k chars (v3) — verify dashboard



### Technical terms

- Saaras is strong on Indian English / code-mix; **not guaranteed** on rare library names.  
- Mitigate with keyterms + deterministic repair (below).  
- Prefer **saaras:v4** + keyterm prompting when available.



### Deterministic transcript correction (no LLM)

1. Build session lexicon at prep (resume/JD + small global tech glossary).
2. On each final user turn: exact → multi-word alias → fuzzy (e.g. rapidfuzz, threshold ~90–92) → optional phonetic with uniqueness checks.
3. Ambiguous ties → do not replace.
4. Persist `raw_text`, `normalized_text`, `corrections[]`.
5. Grill, retrieval, and scoring use **normalized_text**.
6. Do not invent terms outside lexicon (+ small global glossary).

---



## 8. Topics & frontier state machine



### Topic statuses

`planned → active → scored | skipped`

### Frontier node statuses

`locked → available → in_progress → exhausted | abandoned`

### Node fields (conceptual)

- `topic_id`, `parent_id`, `prereqs`  
- `intent` (what is being vetted)  
- `question_mode`: `parallel | direct | escalate`  
- `max_followups`, `followups_used`, `depth_level`



### Loop

Pick highest-priority planned topic → activate → unlock root nodes → ask → score turn → exhaust/abandon per exit criteria → unlock children or rotate topics → wrap → session results.

---



## 9. Database schema (Postgres + pgvector)

Conceptual tables:

- **users** — id, email, name, timestamps  
- **documents** — user_id, type (`resume`|`jd`), R2 key/bucket, parse_status, raw_text  
- **document_sections** — document_id, kind, title, text, ordinal  
- **document_chunks** — section_id, chunk_kind (`bullet`|`role`|`requirement`|…), content, parent linkage, `embedding vector(384)`, metadata jsonb  
- **claims** — document_id, claim_type, text, measurability, priority, source chunk refs  
- **interview_sessions** — user_id, resume/jd doc ids, status (`preparing`|`ready`|`live`|`completed`|`failed`), settings jsonb (duration, difficulty, seniority), n_target, timers, lexicon jsonb  
- **session_topics** — session_id, claim_id?, title, kind, priority, status, soft/hard caps, seconds_spent, rollup_scores  
- **frontier_nodes** — session_id, topic_id, parent_id, status, prereqs, intent, question_mode, followup counters  
- **turns** — session_id, topic_id, frontier_node_id?, role, raw_text, normalized_text, corrections jsonb, timestamps  
- **turn_scores** — turn_id, dimension scores 0–5, confidence, rationale, flags  
- **turn_evidence** — turn_score_id, chunk_id, quote, source  
- **session_results** — overall score, hire_signal, strengths/gaps, coverage_summary  
- **session_reports** — session_id, status (`pending`|`ready`|`failed`), report_json, report_markdown, r2_pdf_key?

Indexes: chunks by document_id; HNSW on embedding; sessions by user; topics/nodes by session + status; turns by session + time.

---



## 10. High-level architecture

```text
Next.js
  → FastAPI
       → R2 (uploads)
       → Postgres/pgvector (docs, chunks, claims, sessions, scores)
       → FastEmbed bge-small (local embeddings)
       → OpenRouter (grill + scoring)
       → Sarvam STT/TTS
       → LiveKit (realtime voice room + agent worker)
```

Agent worker (Python) owns: lexicon normalize → frontier policy → retrieve → LLM → TTS; writes turns/scores to Postgres.

---



## 11. Open items (not locked)

- Auth provider  
- Exact LiveKit Cloud vs self-host split for media  
- Deploy target (VPS/Fly/etc.)  
- OCR for scanned/image-only PDFs (text PDFs supported at MVP)  
- Legacy `.doc` support (MVP is `.docx` only)  
- Exact OpenRouter model IDs for grill vs scoring vs report prose  
- Soft product modes UI (“broad survey” vs “deep dive”)  
- Whether clarify prompts are used when deterministic correction abstains  
- PDF report rendering in MVP vs markdown-only first

---



## 12. Decision log (quick reference)


| Decision          | Choice                                               |
| ----------------- | ---------------------------------------------------- |
| Frontend          | Next.js                                              |
| API               | FastAPI (Python)                                     |
| Voice plumbing    | LiveKit                                              |
| STT / TTS         | Sarvam (Saaras + Bulbul)                             |
| LLM               | OpenRouter                                           |
| Embeddings        | Local bge-small-en-v1.5 (FastEmbed)                  |
| DB / vectors      | Postgres + pgvector                                  |
| Files             | Cloudflare R2                                        |
| Prep timing       | Before interview start                               |
| Chunking          | Section-aware + parent–child                         |
| Interview brain   | Grill-me–style frontier + rounds                     |
| Questions         | Adaptive parallel/direct/escalate                    |
| Coverage          | Time-boxed N topics, anti-rabbit-hole                |
| Scoring           | Rubric v1 dims, evidence-backed                      |
| ASR repair        | Deterministic lexicon/fuzzy only                     |
| Docker philosophy | Light images; external speech APIs; local embeddings |
| Upload formats    | PDF, TXT, DOCX, Markdown, paste                      |
| Upload safety     | 5 MB + sniff; post-extract caps; extract timeout; async prep |
| Doc→LLM trust     | Untrusted data only; role sep; normalize; evidence pack |
| Post-interview    | Structured report (JSON + markdown; PDF optional)    |


