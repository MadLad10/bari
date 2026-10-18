from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from models import Job

log = logging.getLogger("bari.jobs")

Handler = Callable[[Session, dict], dict | None]
HANDLERS: dict[str, Handler] = {}


def handler(kind: str):
    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn
    return register


def enqueue(db: Session, kind: str, payload: dict, dedupe_key: str | None = None, delay_s: float = 0) -> None:
    """Add a job to the caller's session. It's committed with the caller's transaction (no commit here).

    With a dedupe_key, a still-queued job with the same key is not duplicated (e.g. a listing edited
    five times in a row is re-embedded once).
    """
    if dedupe_key:
        pending = [o for o in db.new if isinstance(o, Job) and o.dedupe_key == dedupe_key]
        if pending or db.query(Job.id).filter(Job.dedupe_key == dedupe_key, Job.status == "queued").first():
            return
    job = Job(kind=kind, payload=payload, dedupe_key=dedupe_key)
    if delay_s:
        job.run_after = datetime.now(timezone.utc) + timedelta(seconds=delay_s)
    db.add(job)


def claim_next(db: Session) -> Job | None:
    """Lock and return the oldest runnable job. SKIP LOCKED lets several workers run safely."""
    row = db.execute(text(
        "SELECT id FROM jobs WHERE status = 'queued' AND run_after <= clock_timestamp() "
        "ORDER BY run_after, id LIMIT 1 FOR UPDATE SKIP LOCKED"
    )).first()
    if not row:
        return None
    job = db.get(Job, row.id)
    job.status = "running"
    job.attempts += 1
    db.commit()
    return job


def run_job(db: Session, job: Job) -> None:
    fn = HANDLERS.get(job.kind)
    try:
        if fn is None:
            raise RuntimeError(f"no handler for job kind {job.kind!r}")
        job.result = fn(db, job.payload) or None
        job.status = "done"
        job.last_error = None
    except Exception as e:  # noqa: BLE001
        db.rollback()
        job = db.get(Job, job.id)
        job.last_error = f"{e}\n{traceback.format_exc(limit=3)}"[:4000]
        if job.attempts >= job.max_attempts:
            job.status = "failed"
            log.error("job %s (%s) failed permanently: %s", job.id, job.kind, e)
        else:
            job.status = "queued"
            job.run_after = datetime.now(timezone.utc) + timedelta(seconds=min(300, 2 ** job.attempts))
            log.warning("job %s (%s) attempt %s failed, retrying: %s", job.id, job.kind, job.attempts, e)
    db.commit()


def run_pending(db: Session, limit: int = 1000) -> int:
    """Process runnable jobs synchronously (used by tests, the reindex script and the worker loop)."""
    import jobs.handlers  # noqa: F401  registers handlers
    n = 0
    while n < limit and (job := claim_next(db)):
        run_job(db, job)
        n += 1
    return n
