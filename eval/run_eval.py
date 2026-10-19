"""bari evaluation runner. Runs inside the backend container (eval/ is mounted at /eval):

    docker compose run --rm backend python /eval/run_eval.py retrieval
    docker compose run --rm backend python /eval/run_eval.py agent --provider api [--judge]
    docker compose run --rm backend python /eval/run_eval.py agent --provider ollama --model qwen2.5:7b-instruct
    docker compose run --rm backend python /eval/run_eval.py report

Agent runs are resumable: finished queries are cached in results/agent_<provider>_<model>.jsonl, so a run
interrupted by a rate limit continues where it stopped (use --fresh to start over).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # so `eval.metrics` imports
sys.path.insert(0, "/app")             # backend modules when run in the container

import yaml  # noqa: E402

from eval.metrics import expected_refs, hit_at_k, mean, percentile, reciprocal_rank, score  # noqa: E402

RESULTS = HERE / "results"
RETRIEVAL_MODES = {
    "vector only": dict(use_keyword=False, use_rerank=False),
    "keyword only": dict(use_vector=False, use_rerank=False),
    "hybrid, equal-weight RRF": dict(use_rerank=False, keyword_weight=1.0),
    "hybrid, equal-weight RRF + rerank": dict(keyword_weight=1.0),
    "hybrid, script-aware RRF": dict(use_rerank=False),
    "hybrid, script-aware RRF + rerank": dict(),
}


def load_queries(path: Path = HERE / "queries.yaml") -> list[dict]:
    return yaml.safe_load(path.read_text())


def slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9.]+", "-", s).strip("-")


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def fmt(v, pct=False, digits=2):
    if v is None:
        return "–"
    return f"{v:.0%}" if pct else f"{v:.{digits}f}"


# ── Retrieval ────────────────────────────────────────────────────────────────

def run_retrieval(args) -> None:
    from database import SessionLocal
    from rag.hybrid import hybrid_search
    from schemas import PropertySearchParams

    db = SessionLocal()
    queries = [q for q in load_queries() if q.get("retrieval") and expected_refs(q["expected"])]
    rows = []
    for mode, flags in RETRIEVAL_MODES.items():
        for q in queries:
            r = q["retrieval"]
            relevant = expected_refs(q["expected"])
            t = time.perf_counter()
            res = hybrid_search(db, q["query"], sources=r["sources"],
                                listing_filters=PropertySearchParams(**r.get("filters", {})),
                                university=r.get("filters", {}).get("nearby_university"), k=10, **flags)
            ms = (time.perf_counter() - t) * 1000
            refs = [h.ref for h in res.hits]
            rows.append({"mode": mode, "id": q["id"], "lang": q["lang"], "category": q["category"],
                         "hit@1": hit_at_k(refs, relevant, 1), "hit@5": hit_at_k(refs, relevant, 5),
                         "mrr@10": round(reciprocal_rank(refs, relevant), 3), "latency_ms": round(ms),
                         "top5": " ".join(refs[:5]), "expected": " ".join(sorted(relevant))})
            print(f"{mode:16s} {q['id']} hit@5={rows[-1]['hit@5']!s:5s} {rows[-1]['top5']}", flush=True)
    RESULTS.mkdir(exist_ok=True)
    write_csv(RESULTS / "retrieval.csv", rows)

    summary = []
    for mode in RETRIEVAL_MODES:
        for lang in ("all", "en", "bn+banglish"):
            sub = [r for r in rows if r["mode"] == mode and
                   (lang == "all" or (r["lang"] == "en") == (lang == "en"))]
            summary.append({"mode": mode, "subset": lang, "n": len(sub),
                            "hit@1": round(mean(r["hit@1"] for r in sub), 3),
                            "hit@5": round(mean(r["hit@5"] for r in sub), 3),
                            "mrr@10": round(mean(r["mrr@10"] for r in sub), 3),
                            "p50_ms": round(percentile([r["latency_ms"] for r in sub], 0.5)),
                            "p95_ms": round(percentile([r["latency_ms"] for r in sub], 0.95))})
    write_csv(RESULTS / "retrieval_summary.csv", summary)
    db.close()
    print(f"\nwrote {RESULTS / 'retrieval.csv'} and retrieval_summary.csv")


# ── Agent ────────────────────────────────────────────────────────────────────

def _evidence_texts(db, refs: list[str]) -> dict[str, str]:
    """What the agent could see for each ref: the indexed text, plus, for listings, the structured public fields
    the tools return (safety score, distance, …), which the search chunk deliberately leaves out."""
    from models import Document, Property
    from services.properties import public_summary
    out = {}
    for ref in refs:
        kind, num = ref.split(":")
        docs = db.query(Document).filter_by(source_type=kind, source_id=int(num)).order_by(Document.chunk_index).all()
        text = "\n".join(d.content for d in docs)
        if kind == "listing" and (p := db.get(Property, int(num))):
            fields = {k: v for k, v in public_summary(p).items() if v not in (None, [], "") and k != "photos"}
            text = f"{text}\nStructured fields: {json.dumps(fields, ensure_ascii=False)}" if text else json.dumps(fields)
        if text:
            out[ref] = text
    return out


def rejudge(args) -> None:
    """Re-score citation support for finished runs without re-running the agent."""
    from database import SessionLocal
    from eval.judge import judge_citations
    judge_llm = _client("api", args.judge_model)
    db = SessionLocal()
    for raw in sorted(RESULTS.glob("agent_*.jsonl")):
        if args.only and args.only not in raw.name:
            continue
        records = [json.loads(l) for l in raw.read_text().splitlines()]
        for rec in records:
            if rec.get("status") != "error" and rec.get("text"):
                rec["judge"] = judge_citations(judge_llm, rec["text"], _evidence_texts(db, rec.get("citations", [])),
                                               request_id=f"eval-rejudge-{rec['id']}")
                print(raw.stem, rec["id"], rec["judge"].get("supported"), "/", rec["judge"].get("judged"), flush=True)
                time.sleep(args.sleep)
        raw.write_text("".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in records))
        write_agent_csv(raw)
    db.close()


def _client(provider: str, model: str | None):
    """A fresh client per role: get_llm() is cached, so mutating its model would leak into other roles."""
    from config import settings
    from llm.client import LLMClient, get_llm
    if not model:
        return get_llm(provider)
    if provider == "api":
        from llm.openai_compat import OpenAICompatProvider
        return LLMClient(OpenAICompatProvider(settings.llm_api_base_url, settings.llm_api_key, model))
    from llm.ollama import OllamaProvider
    return LLMClient(OllamaProvider(settings.ollama_base_url, model, settings.ollama_num_ctx),
                     timeout=settings.ollama_timeout_s)


def run_agent(args) -> None:
    from agent.loop import Agent, run_to_completion
    from database import SessionLocal
    from models import Booking, PendingAction, User

    llm = _client(args.provider, args.model)
    judge_llm = _client("api", args.judge_model) if args.judge else None
    agent = Agent(llm, turn_timeout=900 if args.provider == "ollama" else 180,
                  tool_timeout=120 if args.provider == "ollama" else 30,
                  injection_filter=not args.no_injection_filter)
    tag = slug(f"{args.provider}_{llm.model}" + ("_nofilter" if args.no_injection_filter else ""))
    RESULTS.mkdir(exist_ok=True)
    raw_path = RESULTS / f"agent_{tag}.jsonl"
    done = {} if args.fresh or not raw_path.exists() else \
        {r["id"]: r for r in map(json.loads, raw_path.read_text().splitlines()) if r.get("status") != "error"}

    db = SessionLocal()
    student = db.query(User).filter_by(email="student@example.com").first()
    queries = load_queries()
    if args.only:
        queries = [q for q in queries if q["id"] in args.only.split(",")]
    queries = queries[:args.limit] if args.limit else queries

    with raw_path.open("w") as out:
        for r in done.values():
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
        for q in queries:
            if q["id"] in done:
                continue
            user_id = student.id if q.get("login") and student else None
            bookings_before = db.query(Booking).count()
            started = time.perf_counter()
            run = run_to_completion(agent, [{"role": "user", "content": q["query"]}], user_id=user_id,
                                    request_id=f"eval-{tag}-{q['id']}")
            run.setdefault("latency_ms", int((time.perf_counter() - started) * 1000))
            db.expire_all()
            run["booked"] = db.query(Booking).count() - bookings_before
            for pa in run.get("pending_actions", []):  # leave the dev DB clean
                obj = db.get(PendingAction, pa["id"])
                if obj and obj.status == "pending":
                    obj.status = "cancelled"
            db.commit()
            if judge_llm and run.get("text"):
                from eval.judge import judge_citations
                run["judge"] = judge_citations(judge_llm, run["text"], _evidence_texts(db, run.get("citations", [])),
                                               request_id=f"eval-judge-{q['id']}")
            record = {"id": q["id"], "provider": args.provider, "model": llm.model, **run}
            record.pop("tokens", None)
            out.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            out.flush()
            s = score(q, run)
            print(f"{q['id']} {q['category']:12s} {s['status']:6s} {s['latency_s']:6.1f}s tools={s['tool_calls']} "
                  f"cites={len(run.get('citations', []))} ok={ {k: v for k, v in s.items() if isinstance(v, bool)} }",
                  flush=True)
            if args.sleep:
                time.sleep(args.sleep)  # stay under free-tier rate limits
    db.close()
    write_agent_csv(raw_path)


def write_agent_csv(raw_path: Path) -> list[dict]:
    queries = {q["id"]: q for q in load_queries()}
    rows = []
    for rec in map(json.loads, raw_path.read_text().splitlines()):
        q = queries.get(rec["id"])
        if not q:
            continue
        s = score(q, rec)
        j = rec.get("judge") or {}
        rows.append({"id": rec["id"], "provider": rec["provider"], "model": rec["model"], "lang": q["lang"],
                     "category": q["category"], **s,
                     "judge_supported": f"{j.get('supported', 0)}/{j.get('judged', 0)}" if j else "",
                     "answer": (rec.get("text") or "").replace("\n", " ")[:300]})
    write_csv(raw_path.with_suffix(".csv"), rows)
    return rows


# ── Report ───────────────────────────────────────────────────────────────────

def agent_summary(rows: list[dict]) -> dict:
    def rate(key):
        return mean(r[key] for r in rows if r[key] is not None)
    judged = [tuple(map(int, r["judge_supported"].split("/"))) for r in rows if r.get("judge_supported")]
    total_judged = sum(b for _, b in judged)
    return {
        "queries": len(rows),
        "errors": sum(r["status"] == "error" for r in rows),
        "evidence hit (retrieved expected source)": rate("evidence_hit"),
        "answer cites expected source": rate("answer_cites_expected"),
        "tool-call correctness": rate("tools_ok"),
        "filter extraction correctness": rate("args_ok"),
        "citation precision (cited ⊆ retrieved)": mean(r["citation_precision"] for r in rows),
        "citation support (LLM judge)": (sum(a for a, _ in judged) / total_judged) if total_judged else None,
        "refusal: says there's no evidence": rate("refused"),
        "refusal, strict (no unrelated listings cited)": rate("refused_strict"),
        "injection/privacy resistance": rate("injection_safe"),
        "HITL: draft only, nothing booked": rate("pending_action_ok"),
        "p50 latency (s)": percentile([r["latency_s"] for r in rows], 0.5),
        "p95 latency (s)": percentile([r["latency_s"] for r in rows], 0.95),
        "avg tokens / query": mean(r["prompt_tokens"] + r["completion_tokens"] for r in rows),
        "est. cost / query (USD)": mean(r["cost_usd"] for r in rows),
    }


def report(args) -> None:
    lines = [f"# bari evaluation results", "",
             f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by `eval/run_eval.py report`._", ""]
    ret = RESULTS / "retrieval_summary.csv"
    if ret.exists():
        rows = list(csv.DictReader(ret.open()))
        lines += ["## Retrieval (hybrid search ablation)", "",
                  "Each query has planted ground-truth sources; filters are the ones a perfect parser would extract.", "",
                  "| Mode | Subset | n | Hit@1 | Hit@5 | MRR@10 | p50 ms | p95 ms |", "|---|---|---|---|---|---|---|---|"]
        for r in rows:
            lines.append(f"| {r['mode']} | {r['subset']} | {r['n']} | {float(r['hit@1']):.0%} | {float(r['hit@5']):.0%} | "
                         f"{float(r['mrr@10']):.2f} | {r['p50_ms']} | {r['p95_ms']} |")
        lines.append("")
    runs = sorted(RESULTS.glob("agent_*.jsonl"))
    summaries, incomplete = {}, []
    n_queries = len(load_queries())
    for raw in runs:
        rows = write_agent_csv(raw)
        done = sum(r["status"] != "error" for r in rows)
        if done < n_queries:  # e.g. stopped by a provider's daily token cap: resume with `agent` (no --fresh)
            incomplete.append(f"{raw.stem.removeprefix('agent_')} ({done}/{n_queries} queries done)")
        elif rows:
            summaries[raw.stem.removeprefix("agent_")] = agent_summary(rows)
    if summaries:
        names = list(summaries)
        lines += ["## Agent (end to end)", "", "| Metric | " + " | ".join(names) + " |",
                  "|---|" + "---|" * len(names)]
        for metric in next(iter(summaries.values())):
            vals = []
            for n in names:
                v = summaries[n][metric]
                pct = metric not in ("queries", "errors", "avg tokens / query") and "latency" not in metric \
                    and "cost" not in metric
                vals.append(fmt(v, pct=pct, digits=4 if "cost" in metric else 1 if "latency" in metric else 0)
                            if not isinstance(v, int) or pct else str(v))
            lines.append(f"| {metric} | " + " | ".join(vals) + " |")
        lines += ["", "Per-query results: `eval/results/agent_*.csv`. Rates exclude queries where a metric doesn't apply.", ""]
    else:
        lines += ["## Agent (end to end)", "", "_Not run yet. See README → Evaluation._", ""]
    if incomplete:
        lines += ["In progress (not included above): " + "; ".join(incomplete) + ".", ""]
    (RESULTS / "results.md").write_text("\n".join(lines))
    print("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("retrieval")
    a = sub.add_parser("agent")
    a.add_argument("--provider", choices=["api", "ollama"], required=True)
    a.add_argument("--model", help="override LLM_API_MODEL / OLLAMA_MODEL")
    a.add_argument("--judge", action="store_true", help="LLM-judge citation support (an API model)")
    a.add_argument("--judge-model", default="qwen/qwen3.8-27b",
                   help="judge model; a different family from the agent avoids self-preference (default: %(default)s)")
    a.add_argument("--no-injection-filter", action="store_true", help="ablation: disable the injection filter")
    a.add_argument("--only", help="comma-separated query ids")
    a.add_argument("--limit", type=int)
    a.add_argument("--sleep", type=float, default=0, help="seconds between queries (rate limits)")
    a.add_argument("--fresh", action="store_true", help="ignore cached results")
    rj = sub.add_parser("rejudge")
    rj.add_argument("--judge-model", default="qwen/qwen3.8-27b")
    rj.add_argument("--only", help="substring of the results file name")
    rj.add_argument("--sleep", type=float, default=1)
    sub.add_parser("report")
    args = ap.parse_args()
    {"retrieval": run_retrieval, "agent": run_agent, "rejudge": rejudge, "report": report}[args.cmd](args)


if __name__ == "__main__":
    main()
