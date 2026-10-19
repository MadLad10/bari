"""Embed and index every searchable row. Idempotent: unchanged chunks are skipped.

    python -m scripts.reindex            # all sources
    python -m scripts.reindex listing    # one source type

Sources are embedded in groups (one batched API call per group), and a rate-limited group is retried
after a pause, so a free-tier embedding API (e.g. Gemini on the production database) can index everything.
"""
import sys
import time

from database import SessionLocal
from llm.base import LLMError
from rag.indexer import all_sources, index_many

GROUP = 40
PAUSE_S = 60
MAX_RETRIES = 10


def main() -> None:
    only = set(sys.argv[1:])
    db = SessionLocal()
    try:
        sources = [s for s in all_sources(db) if not only or s[0] in only]
        started, embedded = time.perf_counter(), 0
        for i in range(0, len(sources), GROUP):
            group = sources[i:i + GROUP]
            for attempt in range(MAX_RETRIES + 1):
                try:
                    embedded += index_many(db, group)["embedded"]
                    break
                except LLMError as e:
                    if not e.retryable or attempt == MAX_RETRIES:
                        raise
                    print(f"rate limited ({e}); pausing {PAUSE_S}s", flush=True)
                    time.sleep(PAUSE_S)
            print(f"{min(i + GROUP, len(sources))}/{len(sources)} sources, {embedded} chunks embedded, "
                  f"{time.perf_counter() - started:.0f}s", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
