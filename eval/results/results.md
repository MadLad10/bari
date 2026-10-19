# bari evaluation results

_Generated 2026-10-19 18:11 UTC by `eval/run_eval.py report`._

## Retrieval (hybrid search ablation)

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

## Agent (end to end)

| Metric | ollama-qwen2.5-3b-instruct | ollama-qwen2.5-7b-instruct |
|---|---|---|
| queries | 33 | 33 |
| errors | 0 | 0 |
| evidence hit (retrieved expected source) | 59% | 55% |
| answer cites expected source | 36% | 55% |
| tool-call correctness | 88% | 88% |
| filter extraction correctness | 40% | 80% |
| citation precision (cited ⊆ retrieved) | 82% | 96% |
| citation support (LLM judge) | – | – |
| refusal: says there's no evidence | 25% | 25% |
| refusal, strict (no unrelated listings cited) | 25% | 0% |
| injection/privacy resistance | 100% | 100% |
| HITL: draft only, nothing booked | 100% | 100% |
| p50 latency (s) | 75.1 | 88.3 |
| p95 latency (s) | 165.6 | 262.5 |
| avg tokens / query | 6287 | 5473 |
| est. cost / query (USD) | 0.0000 | 0.0000 |

Per-query results: `eval/results/agent_*.csv`. Rates exclude queries where a metric doesn't apply.

In progress (not included above): api-openai-gpt-oss-120b (1/33 queries done); api-openai-gpt-oss-20b (12/33 queries done); api-qwen-qwen3.8-27b (13/33 queries done).
