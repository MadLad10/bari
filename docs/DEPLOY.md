# Deploying bari on Vercel (free)

```
Browser ──► Vercel project with two Services (vercel.json)
              ├─ "web": Vite React build, every path except /api and /uploads
              └─ "api": FastAPI from backend/ (main:app), /api/* and /uploads/*, SSE streaming
              ├─► Neon Postgres + pgvector (free, connected via the Vercel integration)
              ├─► Groq (LLM, free tier)
              └─► Gemini embeddings (free tier); if rate-limited, search falls back to keyword-only
```

What runs differently than locally, and why:

| Local (docker compose) | On Vercel | Why |
|---|---|---|
| bge-m3 via Ollama | `gemini-embedding-001` (1024-d) | a function can't hold a 1.2 GB model |
| bge-reranker-v2-m3 | off (`RERANKER=none`) | ONNX model too large; the eval shows hit@5 0.95 without it |
| `worker` process | jobs run inline at the end of each write request | no always-on processes |
| owner chat over WebSocket | REST polling every 4 s (automatic fallback) | functions can't hold sockets |
| photo uploads on disk | `/tmp` (ephemeral) | the only writable path |

The backend picks these defaults itself when Vercel's `VERCEL=1` is present (`backend/config.py`).

## 1. Accounts and keys (all free)

1. **Gemini API key**: https://aistudio.google.com/apikey → *Create API key*.
2. **Vercel**: https://vercel.com → sign up with GitHub.
3. **Groq**: you already have one (`LLM_API_KEY`). Groq's limits are per organization, so the live demo and the
   eval share the same daily quota.

## 2. Create the project and the database

1. Vercel dashboard → **Add New… → Project** → import `MadLad10/bari`. The framework preset is detected (Vite).
   Leave the build settings as they are; `vercel.json` sets them.
2. In the project: **Storage → Create Database → Neon** (free plan) → connect it to the project. This adds
   `DATABASE_URL` (pooled) and `DATABASE_URL_UNPOOLED` to the project's environment variables.
3. Copy the **unpooled** connection string (Storage → your Neon database → `.env.local` tab) into your local
   `~/yaad_ws/bari/.env` as:
   ```
   NEON_DATABASE_URL='postgresql://…'   # quoted: the URL contains '&'
   GEMINI_API_KEY=…
   ADMIN_PASSWORD=<a long secret: the demo password is public>
   ```

## 2b. Functions run next to the database

`vercel.json` sets `"regions": ["sin1"]` (Singapore), where the Neon database is. Without it, functions would run
in Washington, D.C. and every database query would cross the Pacific. The Hobby plan allows one region, so don't
select extra regions in the dashboard (that's a Pro feature).

## 3. Load the database (once, from your machine)

Schema, synthetic data and the search index (embedded with Gemini, about 25 batched requests):

```bash
cd ~/yaad_ws/bari
set -a; . ./.env; set +a
docker compose run --rm -e DATABASE_URL="$NEON_DATABASE_URL" -e EMBEDDING_PROVIDER=gemini \
  -e GEMINI_API_KEY -e ADMIN_PASSWORD backend \
  sh -c "alembic upgrade head && python seed.py --reset && python -m scripts.reindex"
```

If Gemini rate-limits, the reindex script pauses and resumes on its own.

## 4. Environment variables (Vercel → Settings → Environment Variables, Production)

| Name | Value |
|---|---|
| `LLM_API_KEY` | your Groq key |
| `LLM_API_MODEL` | `openai/gpt-oss-20b` (or `openai/gpt-oss-120b`) |
| `JWT_SECRET` | a long random string: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `EMBEDDING_PROVIDER` | `gemini` |
| `GEMINI_API_KEY` | your Gemini key |
| `ADMIN_PASSWORD` | the same secret as in step 2 |
| `AI_RATE_LIMIT_PER_HOUR` | `20` (assistant turns per user or IP per hour) |
| `CRON_SECRET` | a long random string. Vercel Cron sends it to `/api/cron/scout`, Scout's daily run (09:00 Dhaka) |

`DATABASE_URL` comes from the Neon integration. Then **Deployments → Redeploy**.

## 5. Check it

- `https://<your-app>.vercel.app/api/health` → `{"status":"ok"}`
- Open the site, log in as `student@example.com` / `bari-demo-123`, and ask the assistant
  "2-bed near BRAC under 25k, women-only, from January".
- `/admin` with `admin@example.com` and your `ADMIN_PASSWORD`.

## Limits of the free setup

- Groq free tier: about 200K tokens per model per day, roughly 30 assistant turns. The rate limit stops one
  visitor from using it all.
- Neon free: scales to zero when idle, so the first request after a pause takes a second or two longer.
- Python functions on Fluid compute default to a 300 s duration, plenty for an assistant turn or a Scout run.
- Uploaded photos don't persist (no object storage in this setup).
