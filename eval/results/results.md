# bari evaluation results

_Generated 2026-10-18 18:13 UTC by `eval/run_eval.py report`._

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

_Not run yet. See README → Evaluation._
