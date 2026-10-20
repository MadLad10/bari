# bari: AI housing assistant for students in Dhaka

**An AI assistant that helps university students in Dhaka, Bangladesh find safe, affordable housing. It
searches listings, safety reviews and a community forum in English and Bangla, shows where every answer
comes from, and never books anything without the student's approval.**

**Live demo:** https://bari-mad-lad.vercel.app
(log in as `student@example.com`, password `bari-demo-123`)

![Python](https://img.shields.io/badge/Python-3.12-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688)
![React](https://img.shields.io/badge/React-18-61DAFB) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-336791)
![LangGraph](https://img.shields.io/badge/LangGraph-agent-1C3C3C) ![Vercel](https://img.shields.io/badge/Deployed-Vercel-black)

---

## What it does

- **Ask in plain words, in English or Bangla.** "2-bed near BRAC under 25k, women-only, safe area, from January"
  works, and so does "ধানমন্ডি লেকের পাশে মেয়েদের রুম".
- **Get answers with sources.** Every recommendation links to the listing, safety review or forum post it
  comes from. If there's no evidence, the assistant says so instead of guessing.
- **Book safely.** The assistant can prepare a booking, but only the student's own click on *Confirm*
  makes it real.
- **Let an agent keep looking (Scout).** A student saves what they want once. Every day Scout checks new
  listings, reads safety reviews and forum posts, and prepares questions for owners and a booking, all
  waiting for the student's approval.
- **Help owners and moderators.** Owners get help writing listings and checking their price. Duplicate and
  scam listings, and abusive or spam posts, are flagged automatically for an admin to review.

## What I built

bari started as a university course project: a rental website with a basic chatbot that pasted 20 listings
into a prompt. I rebuilt it into a full AI system:

- **AI assistant (agent).** Replaced the chatbot with an assistant that decides which of 9 tools to use (search,
  safety check, availability, price, booking…), streams its progress live, and cites every claim.
- **Search over English and Bangla text (RAG).** Combined meaning-based search (vector embeddings), keyword
  search and filters, then re-ranked the results. Found and fixed a problem where Bangla searches failed half the
  time: Bangla search success went from 50% to 100%.
- **Safety by design.** Booking needs the user's click. Contact details never reach the AI. Fake
  "instructions" hidden in forum posts (prompt injection) are blocked. These held in **100%** of tests with
  every model, including small local ones.
- **Background agent with LangGraph (Scout).** Runs on a schedule, pauses for the student's approval, and
  resumes days later where it left off, with its state saved in Postgres.
- **Owner and moderation tools.** Listing assistant, duplicate/scam detection (cut false alarms from 48 to 16
  by checking listing details, not just text similarity), and content moderation with logged reasons.
- **Evaluation.** 33 test questions in English and Bangla, measuring search quality, correct tool use,
  citation accuracy, honest "I don't know" answers, injection resistance, speed and cost. I ran it on
  cloud and local models, and fixed 10+ problems it uncovered.
- **Platform work.** Moved the app from SQLite to PostgreSQL, added login, background jobs, 157 automated tests
  (149 backend + 8 frontend), and a free production deployment on Vercel with Neon Postgres.

## Tech stack

| Area | Tools |
|---|---|
| **Languages** | Python 3.12, JavaScript (React), SQL |
| **Backend** | FastAPI, SQLAlchemy 2, Alembic (migrations), Pydantic, JWT authentication, Server-Sent Events (streaming) |
| **AI agents** | Custom tool-calling agent (chat assistant), LangGraph (Scout background agent, human-in-the-loop) |
| **LLMs** | Groq API (`gpt-oss-120b`, `gpt-oss-20b`), local models with Ollama (`qwen2.5` 3B and 7B) |
| **Search / RAG** | PostgreSQL pgvector (vector search), full-text search, pg_trgm, `bge-m3` and Gemini embeddings, `bge-reranker-v2-m3` re-ranker (ONNX) |
| **Database** | PostgreSQL 16+ with pgvector, Neon (production) |
| **Frontend** | React 18, Vite, React Router |
| **Infrastructure** | Docker Compose (local), Vercel (Services + Cron), Neon serverless Postgres |
| **Testing & evaluation** | pytest, Vitest, React Testing Library, custom evaluation harness with an LLM judge |

## Results

| What was measured | Result |
|---|---|
| Blocks prompt-injection and privacy attacks | **100%** (every model tested) |
| Never books without the user's click | **100%** |
| Picks the right tools and understands filters (budget, women-only, university) | **100%** (cloud model) |
| Search finds the right source in the top 5 results | **100%** (22 test searches, English + Bangla) |
| Citations point to real, retrieved sources | **100%** (cloud model) |

Measured on a laptop. The full numbers, including where small local models fall short, are in
[Evaluation details](#evaluation-details) and [`eval/RUNS.md`](eval/RUNS.md).

## Screenshots

| Admin review queue | Listing assistant |
|---|---|
| ![Flagged listings and held posts with reasons](docs/screenshots/admin-review-queue.png) | ![Description draft, missing info and price check](docs/screenshots/listing-assistant.png) |

## How it works

```mermaid
flowchart LR
  U[Student's browser<br/>React] -->|questions, live updates| API[FastAPI backend]
  API --> AG[AI assistant<br/>9 tools]
  API --> SC[Scout<br/>LangGraph background agent]
  AG --> S[Search<br/>vector + keyword + filters]
  SC --> S
  S --> DB[(PostgreSQL<br/>pgvector)]
  AG --> LLM[LLM<br/>Groq or Ollama]
  SC --> LLM
  AG -->|draft only| P[Pending booking]
  U -->|clicks Confirm| P
```

1. The student types a request. The assistant (an LLM) decides which tools to call: search listings, check
   safety, check dates, compute a price.
2. The tools use the same code as the website, so the AI can't do anything the app itself doesn't allow.
3. Search combines meaning-based matching (embeddings), keyword matching and filters such as budget and
   women-only.
4. The answer streams back with numbered sources. Any source the tools didn't actually return is removed.
5. To book, the assistant only creates a draft. The student reviews it and clicks Confirm.

## Run it locally

You need Docker and Node.js 20+. Python runs inside Docker.

```bash
cp .env.example .env
# Add a free Groq API key (https://console.groq.com → API Keys) to .env as LLM_API_KEY=...
docker compose up -d db ollama
docker compose exec ollama ollama pull bge-m3                    # embedding model (required)
docker compose exec ollama ollama pull qwen2.5:7b-instruct       # local LLM (optional)
docker compose run --rm backend sh -c "alembic upgrade head && python seed.py --reset && python -m scripts.reindex"
docker compose up -d backend worker
npm install && npm run dev                                       # http://localhost:5173
```

Demo accounts (password `bari-demo-123`): `student@example.com` (renter), `owner@example.com` (owner of
listings 1–8). The data is synthetic: 150 listings, 200 forum posts and 600+ safety reviews across Dhaka.

**Deploy for free:** one Vercel project with two services (React site + FastAPI), Neon Postgres, Groq and
Gemini. Step by step in [`docs/DEPLOY.md`](docs/DEPLOY.md).

**Tests:**

```bash
docker compose run --rm backend pytest     # 149 backend tests (no API keys or network needed)
npm test                                   # 8 frontend tests
```

---

## Technical details

<details>
<summary><b>Design decisions</b></summary>

| Problem | Solution | Code |
|---|---|---|
| The AI must not duplicate business logic | The website and the AI's tools call the same service functions (search filters, price, availability, booking checks) | `backend/services`, `backend/agent/tools.py` |
| The AI must never book without consent | `draft_booking` only stores a pending action. Only the same user's `POST /api/actions/{id}/confirm` creates the booking. Drafting also requires booking intent in the *user's* message, so an injected post can't trigger it | `agent/tools.py`, `routers/actions.py` |
| Answers must be grounded | Every claim cites a source. Citations to sources the tools didn't return are removed. Budget and women-only constraints are checked against the recommendations | `agent/guardrails.py`, `agent/loop.py` |
| Forum posts can contain prompt injections | User-written text is wrapped as untrusted data, an English/Bangla filter withholds instruction-like content, and the AI has no write tools except the gated draft | `agent/guardrails.py` |
| Privacy | Tools never receive owner phone numbers or emails; answers are scrubbed for phones (Latin and Bangla digits) and emails | `services/properties.py`, `agent/guardrails.py` |
| Bangla search without a Bangla stemmer | Multilingual embeddings, plus full-text search with prefix matching (`ছাত্রী:*` matches `ছাত্রীদের`) and trigram matching | `rag/hybrid.py` |
| Search must respect hard limits | Filters are applied in SQL before ranking; vector and keyword results are merged (Reciprocal Rank Fusion, weighted by script), then re-ranked | `rag/hybrid.py` |
| Keep the search index up to date reliably | Index jobs are saved in the same transaction as the data change (outbox pattern); a Postgres job queue with retries; unchanged text is never re-embedded | `jobs/`, `rag/indexer.py` |
| LLM calls are slow, flaky and cost money | One interface for Groq and Ollama, retries with backoff, timeouts, and every call logged with tokens, time and cost | `llm/` |
| A background agent must wait for people | Scout's approval step is a LangGraph `interrupt()`; its state is saved in Postgres by the LangGraph checkpointer | `backend/scout/` |
| Moderation must be explainable | Rules decide, the LLM gives a second opinion, and every decision is stored with its reasons for admin review | `workflows/` |

</details>

<details>
<summary><b>Scout: the background agent (LangGraph)</b></summary>

A student saves a hunt ("2-bed near BRAC under 25k, women-only, from January, quiet street; ask if it has line
gas"). Every day (Vercel Cron, or the worker locally), Scout runs this graph:

```mermaid
flowchart LR
  S([daily cron / Run now]) --> F[find new listings<br/><i>filters, skip seen and rejected</i>]
  F -- nothing new --> E([report: no new matches])
  F --> G[gather evidence<br/><i>safety reviews, forum, availability</i>]
  G --> A[assess with LLM<br/><i>rank against preferences, cite evidence</i>]
  A --> D[draft owner questions<br/>and a booking]
  D -- nothing to approve --> X([done])
  D --> I{{wait for the student<br/>interrupt}}
  I -. approve / discard<br/>hours or days later .-> L[learn<br/><i>rejected listings don't return</i>]
  L --> X
```

- **Pauses for people.** `interrupt()` stops the run, and LangGraph's Postgres checkpointer saves its state.
  When the student decides, maybe days later on another server, the run continues from the checkpoint.
- **The LLM only judges.** Finding listings, collecting evidence and checking dates are normal code. One LLM call
  ranks and explains. If the LLM fails, a rule-based ranking takes over.
- **Messages can't be hijacked.** Questions to owners are filled from the student's own questions, so text in a
  listing can never put words in the student's mouth.
- **Why LangGraph here and not for the chat assistant:** Scout needs saved state and pausing for approval,
  which is what LangGraph is built for. The chat assistant is a short, latency-sensitive loop that is already
  tested and evaluated, so it stays a small custom agent.

</details>

<details>
<summary><b>Evaluation details</b></summary>

`eval/queries.yaml` has 33 questions (24 English, 9 Bangla/Banglish) with known correct answers planted in the
synthetic data: specific needs (rooftop garden, wheelchair access, pet-friendly), filter requests, safety and
forum questions, comparison and pricing, a booking, 4 questions with no answer in the data, and 4
prompt-injection and privacy attacks.

```bash
docker compose run --rm backend python /eval/run_eval.py retrieval                 # search quality
docker compose run --rm backend python /eval/run_eval.py agent --provider api --judge --sleep 3
docker compose run --rm backend python /eval/run_eval.py agent --provider ollama
docker compose run --rm backend python /eval/run_eval.py report                    # → eval/results/results.md
```

Search numbers were measured with the local stack (`bge-m3` + re-ranker). The live site uses Gemini
embeddings without the re-ranker, to fit Vercel's free limits.

<!-- RESULTS:START -->
#### Search quality: full ablation

Each query has planted ground-truth sources; filters are the ones a perfect parser would extract.

| Mode | Subset | n | Hit@1 | Hit@5 | MRR@10 | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|
| vector only | all | 22 | 86% | 96% | 0.90 | 252 | 288 |
| vector only | en | 14 | 86% | 93% | 0.89 | 258 | 343 |
| vector only | bn+banglish | 8 | 88% | 100% | 0.92 | 240 | 270 |
| keyword only | all | 22 | 64% | 82% | 0.69 | 14 | 21 |
| keyword only | en | 14 | 79% | 100% | 0.85 | 16 | 22 |
| keyword only | bn+banglish | 8 | 38% | 50% | 0.42 | 9 | 13 |
| hybrid, equal-weight RRF | all | 22 | 68% | 82% | 0.72 | 262 | 299 |
| hybrid, equal-weight RRF | en | 14 | 79% | 100% | 0.85 | 264 | 293 |
| hybrid, equal-weight RRF | bn+banglish | 8 | 50% | 50% | 0.50 | 258 | 300 |
| hybrid, equal-weight RRF + rerank | all | 22 | 73% | 82% | 0.76 | 2726 | 4205 |
| hybrid, equal-weight RRF + rerank | en | 14 | 86% | 100% | 0.91 | 2394 | 4223 |
| hybrid, equal-weight RRF + rerank | bn+banglish | 8 | 50% | 50% | 0.50 | 3486 | 4147 |
| hybrid, script-aware RRF | all | 22 | 68% | 96% | 0.76 | 378 | 458 |
| hybrid, script-aware RRF | en | 14 | 79% | 100% | 0.85 | 380 | 486 |
| hybrid, script-aware RRF | bn+banglish | 8 | 50% | 88% | 0.60 | 378 | 411 |
| hybrid, script-aware RRF + rerank | all | 22 | 91% | 100% | 0.94 | 3242 | 4748 |
| hybrid, script-aware RRF + rerank | en | 14 | 86% | 100% | 0.91 | 3242 | 4870 |
| hybrid, script-aware RRF + rerank | bn+banglish | 8 | 100% | 100% | 1.00 | 2979 | 3746 |

#### Assistant: full results

Three complete runs, 33 queries each:
- **gpt-oss-20b** via the Groq API. This is a baseline measured *before* the eval-driven fixes in
  [`eval/RUNS.md`](eval/RUNS.md). Citation support was judged by `qwen/qwen3.8-27b`, a different model family.
- **qwen2.5:3b** and **qwen2.5:7b** run locally with Ollama on a laptop CPU, using the current code. They have no
  citation-support number because the judge model's free daily quota had run out.

Re-runs of the API models on the current code are pending: Groq's free tier allows 200K tokens per model per
day, and one run with judging needs about 215K.

| Metric | gpt-oss-20b · API (baseline) | qwen2.5:3b · local | qwen2.5:7b · local |
|---|---|---|---|
| Injection / privacy resistance (4 probes + scam listing) | **100%** | **100%** | **100%** |
| Human-in-the-loop: booking drafted, nothing booked | **100%** | **100%** | **100%** |
| Tool-call correctness | 100% | 88% | 88% |
| Filter extraction (budget, women-only, university, bedrooms) | 100% | 40% | 80% |
| Citation precision (the model's own citations point at retrieved evidence) | 100% | 82% | 96% |
| Citation support (LLM judge) | 100% | – | – |
| Refusal on unanswerable: says there's no evidence | 100% | 25% | 25% |
| Refusal, strict (also cites no unrelated listings) | 75% | 25% | 0% |
| Evidence hit (the expected source was retrieved) | 73% | 59% | 55% |
| Answer cites the expected source | 64% | 36% | 55% |
| p50 / p95 latency | 32 s / 76 s | 75 s / 166 s | 88 s / 263 s |
| Tokens / est. cost per query | 6.5k / $0.0008 | 6.3k / $0 (local) | 5.5k / $0 (local) |

**What the agent eval showed**

- **The safety properties held at 100% even with a 3B model.** The model is not trusted to enforce them; code
  does. Tools never receive contact details. Citations not backed by retrieved evidence are stripped (which is
  why the 3B's raw citation precision is 82% while its users still never see an invalid citation). Drafting a
  booking needs booking intent in the user's own message, and booking needs a click.
- **Model size buys accuracy, not safety:** going from 3B to 7B doubles filter extraction (40% → 80%) and lifts
  citation precision to 96%, while the safety rows are 100% for every model. Neither local model refuses
  unanswerable questions honestly (25%), which is where the API model is clearly ahead.
- **What a small model loses is quality:** filter extraction (40%), honest refusals (25%) and grounded answers
  (36%). The deterministic constraint check flags recommendations that break the user's budget or women-only
  requirement.
- **The API model's weak spot was recall**: answering "no information" without searching, misspelled
  romanised area names, and searching listings for questions the forum answers. The grounding guard, trigram
  area normalisation and forum routing in `eval/RUNS.md` were added because of these failures.
- **Latency on the test laptop is dominated by local work**, not the LLM API: CPU embedding and reranking
  (about 3 s per search) under heavy memory pressure, plus CPU inference for the local model.

**What the retrieval ablation showed**

- **Equal-weight hybrid search was worse than vector search alone**, especially in Bangla (hit@5 0.50 vs 1.00).
  The Bangla queries look for listings written in English; keyword search can't match across languages, and
  Reciprocal Rank Fusion then buries a document that is #1 for vector search but absent from the keyword list.
- Keyword search still helps in English: it rescued a query that vector search missed ("walk around Mohakhali
  at night" → the mugging report).
- The fix is **script-aware fusion**: full keyword weight for Latin-script queries (English and Banglish),
  weight 0.1 for Bangla script, which keeps keyword matches as a tie-breaker. With the bge-reranker-v2-m3
  cross-encoder on the top 10, hit@5 reaches 1.00 and MRR 0.94. ⚠️ The Bangla weight was chosen on the same 7
  Bangla queries it is evaluated on; confirm on a held-out set before trusting the exact number.
- Reranking costs about 3 s per search on a shared laptop CPU (it's the latency driver); `RERANKER=none` drops
  to about 0.4 s at hit@5 0.95 / MRR 0.76.
- Duplicate screening, tuned on the same corpus: embedding similarity alone flagged 48 listing pairs, because
  neighbours share boilerplate (cosine 0.92–0.98). Requiring the copied ad to also repeat the area, size, price
  (±10%) and a similar title brought that down to 16 + the planted copy. The price/scam-text rules flagged only
  the planted scam.
<!-- RESULTS:END -->

</details>

## Project layout

```
backend/
  agent/        AI assistant: tool loop, tools, prompts, guardrails
  scout/        Scout background agent (LangGraph)
  rag/          search: chunking, embeddings, hybrid search, re-ranker, indexer
  llm/          LLM providers (Groq, Ollama), retries, call log, pricing
  workflows/    listing assistant, duplicate/scam screening, moderation
  jobs/         Postgres job queue and worker
  services/     business logic shared by the website and the AI
  routers/      HTTP API
  alembic/      database migrations
  seed_data/    synthetic data generator
  tests/        backend tests
eval/           evaluation questions, runner, metrics, results
src/            React frontend
docs/           deployment guide, screenshots
```

## Limitations and next steps

- **Synthetic data.** The listings and posts are generated, so many look alike. Real data would need re-tuning
  of duplicate detection and a labelled test set.
- **Laptop hardware.** Without a GPU, embedding and re-ranking take a few seconds per search. A GPU or a hosted
  re-ranker would make search faster and deeper.
- **Small local models.** The 3B and 7B models stay safe (100%) but are weaker at understanding filters and at
  saying "I don't know". A cloud model does much better.
- **Next:** bKash payments for confirmed bookings, owner notifications, map search.

## Credits

bari began as a course project (Group 11, CSE471, BRAC University). This version adds the AI assistant, search,
Scout, moderation tools, evaluation and the production deployment.
