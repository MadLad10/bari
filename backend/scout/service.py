"""Start, resume and schedule Scout runs."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from langgraph.types import Command
from sqlalchemy import func
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from jobs.queue import enqueue
from models import Hunt, PendingAction, ScoutRun
from scout.checkpointer import open_checkpointer
from scout.graph import build_graph
from services.errors import Conflict

log = logging.getLogger("bari.scout")
RUN_EVERY = timedelta(days=1)


def _graph(cp):
    return build_graph().compile(checkpointer=cp)


def run_hunt(hunt_id: int, trigger: str = "schedule") -> int | None:
    """Run Scout once for a hunt. Returns the run id (None if the hunt is gone or paused)."""
    db = SessionLocal()
    try:
        hunt = db.get(Hunt, hunt_id)
        if hunt is None or (trigger == "schedule" and hunt.status != "active"):
            return None
        now = datetime.now(timezone.utc)
        run = ScoutRun(hunt_id=hunt.id, thread_id=uuid.uuid4().hex, trigger=trigger)
        hunt.last_run_at, hunt.next_run_at = now, now + RUN_EVERY
        db.add(run)
        db.commit()
        run_id, thread_id = run.id, run.thread_id
    finally:
        db.close()
    try:
        with open_checkpointer() as cp:
            _graph(cp).invoke({"hunt_id": hunt_id, "run_id": run_id}, {"configurable": {"thread_id": thread_id}})
    except Exception as e:  # noqa: BLE001  a failed run is recorded, never raised into the scheduler
        log.exception("scout run %s failed", run_id)
        _fail(run_id, e)
    return run_id


def resume_if_decided(db: Session, run_id: int | None) -> bool:
    """Resume a paused run once every drafted action is decided (approved, discarded or expired)."""
    if run_id is None:
        return False
    run = db.query(ScoutRun).filter(ScoutRun.id == run_id).with_for_update().first()
    if run is None or run.status != "awaiting_approval":
        db.rollback()
        return False
    now = datetime.now(timezone.utc)
    actions = db.query(PendingAction).filter(PendingAction.scout_run_id == run_id).all()
    for a in actions:
        if a.status == "pending" and a.expires_at < now:
            a.status = "expired"
    if any(a.status == "pending" for a in actions):
        db.commit()
        return False
    decisions = {str(a.id): a.status for a in actions}
    run.status = "resuming"  # claimed under the row lock: a concurrent decision won't resume twice
    thread_id = run.thread_id
    db.commit()
    try:
        with open_checkpointer() as cp:
            _graph(cp).invoke(Command(resume=decisions), {"configurable": {"thread_id": thread_id}})
    except Exception as e:  # noqa: BLE001
        log.exception("scout resume %s failed", run_id)
        _fail(run_id, e)
    return True


def _fail(run_id: int, error: Exception) -> None:
    db = SessionLocal()
    try:
        run = db.get(ScoutRun, run_id)
        run.status, run.error, run.finished_at = "failed", str(error)[:1000], datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def enqueue_due_hunts(db: Session) -> int:
    """Queue a run for every active hunt that's due, and resume runs whose drafts all expired."""
    now = datetime.now(timezone.utc)
    due = db.query(Hunt.id).filter(Hunt.status == "active", Hunt.next_run_at <= now).all()
    for (hunt_id,) in due:
        enqueue(db, "scout_run", {"hunt_id": hunt_id, "trigger": "schedule"}, dedupe_key=f"scout:{hunt_id}")
    db.commit()
    stale = db.query(ScoutRun.id).filter(ScoutRun.status == "awaiting_approval",
                                         ScoutRun.started_at < now - timedelta(days=3)).all()
    for (run_id,) in stale:
        resume_if_decided(db, run_id)
    return len(due)


def check_manual_quota(db: Session, user_id: int) -> None:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    used = (db.query(func.count(ScoutRun.id)).join(Hunt, Hunt.id == ScoutRun.hunt_id)
            .filter(Hunt.user_id == user_id, ScoutRun.trigger == "manual", ScoutRun.started_at >= since).scalar())
    if used >= settings.scout_manual_runs_per_day:
        raise Conflict(f"Scout can be run manually {settings.scout_manual_runs_per_day} times a day. "
                       "It also runs automatically every day.")
