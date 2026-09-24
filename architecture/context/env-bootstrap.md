# Env bootstrap

Status: done  
Date: 2026-09-22

## What

Root `.env` (+ commit-safe `.env.example`) with variables required by the PRD stack for local/dev work.

## Variables covered

- App / CORS / `DEV_USER_ID` stub
- Postgres + `DATABASE_URL` (asyncpg)
- Optional `REDIS_URL`
- Cloudflare R2 (S3-compatible; MinIO-friendly endpoint)
- OpenRouter (API key + grill/score/report model slots)
- Local embeddings model id + dims (no key)
- Sarvam STT/TTS
- LiveKit URL + API credentials
- Upload size limit (`MAX_UPLOAD_BYTES`, default 5 MB)
- Paste char limit (`MAX_PASTE_CHARS`)

## Files

- `.env` (gitignored)
- `.env.example` (tracked template)
- `.gitignore` — ignore `.env` / local overrides
