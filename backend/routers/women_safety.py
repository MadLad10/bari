from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from database import get_db
from deps import get_current_user, require_role
from models import Property, User, UserRole
from services import women_safety as svc
from services.properties import get_property
from services.users import ensure_can_manage_property

router = APIRouter(tags=["women-safety"])


class SafetySubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=0)
    checklist: dict[str, bool]
    notes: str = Field(min_length=20, max_length=5000)


class SafetyDecision(SafetySubmission):
    verdict: Literal["approved", "changes_requested", "rejected"]


@router.get("/properties/{property_id}/women-safety")
def owner_summary(property_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    prop = get_property(db, property_id)
    ensure_can_manage_property(user, prop)
    return svc.summary(db, prop)


@router.post("/properties/{property_id}/women-safety")
def submit(property_id: int, payload: SafetySubmission, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.submit(db, property_id, payload, user)


@router.get("/admin/women-safety")
def queue(status: Literal["pending", "approved", "changes_requested", "rejected", "not_submitted", "all"] = "pending",
          limit: int = Query(50, ge=1, le=100), skip: int = Query(0, ge=0),
          db: Session = Depends(get_db), _: User = Depends(require_role(UserRole.admin))):
    query = db.query(Property).filter(Property.is_female_only.is_(True))
    if status != "all":
        query = query.filter(Property.women_safety_status == status)
    return {"total": query.count(), "items": [svc.summary(db, p) for p in query.order_by(Property.id).offset(skip).limit(limit)]}


@router.post("/admin/women-safety/{property_id}")
def decide(property_id: int, payload: SafetyDecision, db: Session = Depends(get_db),
           admin: User = Depends(require_role(UserRole.admin))):
    return svc.decide(db, property_id, payload, admin)
