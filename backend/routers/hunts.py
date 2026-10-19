"""Scout hunts: a student's saved search that a background agent works on."""
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agent.tools import DHAKA, ListingFilters
from config import settings
from database import get_db
from deps import get_current_user
from models import Hunt, PendingAction, ScoutRun, User
from scout import service
from scout.criteria import parse_brief
from services.errors import Forbidden, NotFound

router = APIRouter(tags=["scout"])


class BriefIn(BaseModel):
    brief: str = Field(..., min_length=10, max_length=2000)


class HuntIn(BaseModel):
    title: str = Field(..., min_length=3, max_length=120)
    brief: str = Field(..., min_length=10, max_length=2000)
    criteria: ListingFilters = Field(default_factory=ListingFilters)
    preferences: list[str] = Field(default_factory=list, max_length=8)
    questions: list[str] = Field(default_factory=list, max_length=6)
    move_in: date | None = None
    stay_months: int = Field(6, ge=1, le=24)


class HuntPatch(BaseModel):
    status: str | None = Field(None, pattern="^(active|paused)$")


def _own(db: Session, hunt_id: int, user: User) -> Hunt:
    hunt = db.get(Hunt, hunt_id)
    if not hunt:
        raise NotFound("Hunt not found")
    if hunt.user_id != user.id:
        raise Forbidden("Not your hunt")
    return hunt


def _hunt_out(h: Hunt, latest: ScoutRun | None = None) -> dict:
    return {"id": h.id, "title": h.title, "brief": h.brief, "criteria": h.criteria, "preferences": h.preferences,
            "questions": h.questions, "move_in": h.move_in.astimezone(DHAKA).date().isoformat() if h.move_in else None,
            "stay_months": h.stay_months, "status": h.status,
            "last_run_at": h.last_run_at.isoformat() if h.last_run_at else None,
            "next_run_at": h.next_run_at.isoformat() if h.next_run_at else None,
            "seen": len(h.seen_listing_ids or []),
            "latest_run": _run_out(latest) if latest else None}


def _run_out(r: ScoutRun, actions: list[PendingAction] | None = None) -> dict:
    out = {"id": r.id, "trigger": r.trigger, "status": r.status, "report": r.report, "error": r.error,
           "started_at": r.started_at.isoformat() if r.started_at else None,
           "finished_at": r.finished_at.isoformat() if r.finished_at else None}
    if actions is not None:
        out["actions"] = [{"id": a.id, "type": a.action_type, "status": a.status, "summary": a.summary,
                           "expires_at": a.expires_at.isoformat()} for a in actions]
    return out


@router.post("/hunts/parse")
def parse(payload: BriefIn, user: User = Depends(get_current_user)):
    """Turn the student's own words into a draft hunt they can review before saving."""
    draft = parse_brief(payload.brief)
    return {**draft.model_dump(mode="json"), "criteria": draft.criteria.model_dump(exclude_none=True)}


@router.post("/hunts", status_code=201)
def create_hunt(payload: HuntIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    move_in = datetime.combine(payload.move_in, time(0, 0), tzinfo=DHAKA) if payload.move_in else None
    hunt = Hunt(user_id=user.id, title=payload.title, brief=payload.brief,
                criteria=payload.criteria.model_dump(exclude_none=True), preferences=payload.preferences,
                questions=payload.questions, move_in=move_in, stay_months=payload.stay_months,
                next_run_at=datetime.now(timezone.utc))
    db.add(hunt)
    db.commit()
    return _hunt_out(hunt)


@router.get("/hunts")
def my_hunts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    hunts = db.query(Hunt).filter(Hunt.user_id == user.id).order_by(Hunt.created_at.desc()).all()
    out = []
    for h in hunts:
        latest = db.query(ScoutRun).filter(ScoutRun.hunt_id == h.id).order_by(ScoutRun.id.desc()).first()
        out.append(_hunt_out(h, latest))
    return out


@router.get("/hunts/{hunt_id}")
def get_hunt(hunt_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    hunt = _own(db, hunt_id, user)
    runs = db.query(ScoutRun).filter(ScoutRun.hunt_id == hunt.id).order_by(ScoutRun.id.desc()).limit(20).all()
    actions = db.query(PendingAction).filter(PendingAction.scout_run_id.in_([r.id for r in runs])).all() if runs else []
    by_run: dict[int, list] = {}
    for a in actions:
        by_run.setdefault(a.scout_run_id, []).append(a)
    return {**_hunt_out(hunt), "runs": [_run_out(r, sorted(by_run.get(r.id, []), key=lambda a: a.id)) for r in runs]}


@router.patch("/hunts/{hunt_id}")
def update_hunt(hunt_id: int, payload: HuntPatch, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    hunt = _own(db, hunt_id, user)
    if payload.status:
        hunt.status = payload.status
        if payload.status == "active" and not hunt.next_run_at:
            hunt.next_run_at = datetime.now(timezone.utc)
    db.commit()
    return _hunt_out(hunt)


@router.delete("/hunts/{hunt_id}", status_code=204)
def delete_hunt(hunt_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.delete(_own(db, hunt_id, user))
    db.commit()


@router.post("/hunts/{hunt_id}/run")
def run_now(hunt_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    hunt = _own(db, hunt_id, user)
    service.check_manual_quota(db, user.id)
    db.commit()  # end this read transaction: the run uses its own sessions
    run_id = service.run_hunt(hunt.id, trigger="manual")
    db.expire_all()
    return {**get_hunt(hunt_id, db=db, user=user), "run_id": run_id}


@router.get("/cron/scout")
def cron(authorization: str | None = Header(None), db: Session = Depends(get_db)):
    """Daily trigger (Vercel Cron sends `Authorization: Bearer $CRON_SECRET`). Queues due hunts and runs a few
    inline, because there is no worker on Vercel."""
    if not settings.cron_secret or authorization != f"Bearer {settings.cron_secret}":
        raise Forbidden("Invalid cron secret")
    queued = service.enqueue_due_hunts(db)
    from jobs.queue import run_pending
    processed = run_pending(db, limit=3) if settings.jobs_mode == "inline" else 0
    return {"queued": queued, "processed": processed}
