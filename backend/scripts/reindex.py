"""Embed and index every searchable row. Idempotent: unchanged chunks are skipped.

    python -m scripts.reindex            # all sources
    python -m scripts.reindex listing    # one source type
"""
import sys
import time

from database import SessionLocal
from rag.indexer import all_sources, index_source


def main() -> None:
    only = set(sys.argv[1:])
    db = SessionLocal()
    try:
        sources = [s for s in all_sources(db) if not only or s[0] in only]
        started, embedded = time.perf_counter(), 0
        for i, (kind, sid) in enumerate(sources, start=1):
            embedded += index_source(db, kind, sid)["embedded"]
            if i % 100 == 0 or i == len(sources):
                print(f"{i}/{len(sources)} sources, {embedded} chunks embedded, {time.perf_counter() - started:.0f}s",
                      flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
