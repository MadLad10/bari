# Evaluation log

Every eval run, what it found, and what changed because of it. Raw per-query results are in `results/runs/`.

## 2026-10-19 · retrieval ablation (bge-m3 + bge-reranker-v2-m3)
- Equal-weight RRF hybrid was **worse than vector-only** on Bangla queries (hit@5 0.50 vs 1.00): keyword search
  can't match a Bangla query to an English listing, and RRF buries the vector #1.
- Fix: script-aware keyword weight (Latin 1.0, Bangla 0.1). Hybrid + rerank: hit@5 1.00, MRR 0.94 (22 queries).
  Caveat: the Bangla weight was swept on the same 7 Bangla queries.

## 2026-10-19 · agent, openai/gpt-oss-120b (first run)
- Found: `null` optional tool args failed Groq's server-side schema validation (whole turn lost); invented
  `area` filter → empty results; English question answered in Bangla; at the tool limit the model still called a
  tool, and Groq rejected the forced final answer.
- Fixes: nullable schemas, transparent relaxation of guessed filters, language rule, forced-answer retry +
  evidence fallback.
- Metric bugs found and fixed: refusal regex missed curly apostrophes; the citation judge split "0.6 km" into
  "6 km" and judged multi-source claims per source. A re-run then hit Groq's free-tier cap (200K tokens/day for
  this model; one full run with judging is about 215K), so the 120b run continues when the quota resets.

## 2026-10-19 · agent, openai/gpt-oss-20b, judge qwen/qwen3.8-27b → `runs/2026-10-19_gpt-oss-20b_baseline/`
Tool-call and filter-extraction correctness 100%, citation precision 100%, judge-rated citation support 100%,
injection/privacy resistance 100%, HITL 100%, refusal 100% (75% strict), evidence hit 73%, p50 32 s.
- Found: answered "I don't have any data" **without searching** (q11); misspelled romanised area "Boshundhara"
  → no forum hits (q18); a guessed `listing_type` that still returned results hid the right listing (q17);
  searched listings for roommate/scam questions the forum answers (q12, q13).
- Fixes: grounding guard (a "no information" answer before any tool call triggers one search nudge), pg_trgm
  area normalisation, forum filter relaxation, a prompt rule on when to use `search_forum`.
  Spot-check with the same model: q11, q17, q18 fixed; q12, q13 still choose listing search (model limit).

## 2026-10-19 · agent, qwen/qwen3.8-27b (partial, 13/33 on current code)
- Found: the model sent `"true"` (a string) for a boolean; Groq's server-side schema check rejected the call and
  the turn failed. Fix: provider-rejected tool calls are fed back to the model and retried (max 2 per turn).
- Under memory pressure on the test laptop (swap full, Duburi's Ollama instances resident), local embedding and
  reranking slowed to over 30 s per search and one turn timed out: an infrastructure failure, not an agent one.
  The runner now has `--tool-timeout` / `--turn-timeout`.
- The run then hit this model's free-tier cap (200K tokens/day) as well. Re-runs of all three models on the
  current code resume when the quotas reset (`run_eval.py agent …` without `--fresh`).
