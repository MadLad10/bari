from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from database import get_db
from deps import get_current_user, require_role
from models import User, UserRole
from services import cases as svc

router = APIRouter(tags=["investigations"])
admin_only = require_role(UserRole.admin)
Status = Literal["open", "investigating", "awaiting_reporter", "resolved", "dismissed"]
Category = Literal["unsafe_listing", "booking_dispute", "forum_report", "other"]


class CaseIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    category: Literal["unsafe_listing", "booking_dispute", "other"]
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=10, max_length=15000)
    property_id: int | None = Field(default=None, gt=0)
    booking_id: int | None = Field(default=None, gt=0)


class MessageIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    body: str = Field(min_length=2, max_length=10000)


class NoteIn(MessageIn):
    internal: bool = True


class VersionIn(BaseModel):
    expected_version: int = Field(ge=1)


class DecisionIn(VersionIn):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    status: Status
    message: str = Field(min_length=5, max_length=10000)
    hold_listing: bool = False


@router.post("/cases", status_code=201)
def create_case(payload: CaseIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    case = svc.create_case(db, user, **payload.model_dump())
    return svc.detail(db, case, user)


@router.get("/cases/mine")
def my_cases(status: Status | None = None, skip: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
             db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [svc.summary(db, row) for row in svc.list_cases(db, user, status=status, skip=skip, limit=limit, mine=True)]


@router.get("/cases/{case_id}")
def case_detail(case_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.detail(db, svc.get_case(db, case_id, user), user)


@router.post("/cases/{case_id}/messages")
def reporter_message(case_id: int, payload: MessageIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.detail(db, svc.add_update(db, case_id, user, payload.body), user)


@router.get("/admin/cases")
def admin_cases(status: Status | None = None, category: Category | None = None, q: str | None = None,
                skip: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
                db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return [svc.summary(db, row, admin=True) for row in svc.list_cases(db, user, status=status, category=category,
                                                                    q=q, skip=skip, limit=limit)]


@router.post("/admin/cases/{case_id}/claim")
def claim(case_id: int, payload: VersionIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return svc.detail(db, svc.claim(db, case_id, user, payload.expected_version), user)


@router.post("/admin/cases/{case_id}/notes")
def note(case_id: int, payload: NoteIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return svc.detail(db, svc.add_update(db, case_id, user, payload.body, internal=payload.internal), user)


@router.patch("/admin/cases/{case_id}")
def decision(case_id: int, payload: DecisionIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return svc.detail(db, svc.decide(db, case_id, user, **payload.model_dump()), user)
