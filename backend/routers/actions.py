"""Human-in-the-loop: the agent drafts actions, and only these endpoints, called by the user's own
click, execute them."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from deps import get_current_user
from models import PendingAction, RentalType, User
from services import bookings as booking_svc
from services.bookings import BookingCreate
from services.errors import BadRequest, Conflict, Forbidden, NotFound, ServiceError

router = APIRouter(prefix="/actions", tags=["actions"])


class ConfirmIn(BaseModel):
    renter_phone: str | None = Field(None, min_length=11, max_length=20)
    note: str | None = Field(None, max_length=300)


def _out(a: PendingAction) -> dict:
    return {"id": a.id, "type": a.action_type, "status": a.status, "summary": a.summary, "result": a.result,
            "expires_at": a.expires_at.isoformat(), "created_at": a.created_at.isoformat() if a.created_at else None}


def _load(db: Session, action_id: int, user: User, lock: bool = False) -> PendingAction:
    q = db.query(PendingAction).filter(PendingAction.id == action_id)
    action = (q.with_for_update() if lock else q).first()
    if not action:
        raise NotFound("Action not found")
    if action.user_id != user.id:
        raise Forbidden("This action belongs to another user")
    return action


def _ensure_pending(db: Session, action: PendingAction) -> None:
    if action.status == "pending" and action.expires_at < datetime.now(timezone.utc):
        action.status = "expired"
        db.commit()
    if action.status != "pending":
        raise Conflict(f"Action is already {action.status}")


@router.get("/{action_id}")
def get_action(action_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _out(_load(db, action_id, user))


@router.post("/{action_id}/confirm")
def confirm(action_id: int, body: ConfirmIn | None = None, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    body = body or ConfirmIn()
    action = _load(db, action_id, user, lock=True)
    _ensure_pending(db, action)
    if action.action_type != "create_booking":
        raise BadRequest(f"Unsupported action {action.action_type}")
    phone = body.renter_phone or user.phone
    if not phone:
        raise BadRequest("A phone number is required to book")
    p = action.payload
    booking_in = BookingCreate(property_id=p["property_id"], renter_name=user.name, renter_phone=phone,
                               renter_email=user.email, check_in=datetime.fromisoformat(p["check_in"]),
                               check_out=datetime.fromisoformat(p["check_out"]), rental_type=RentalType(p["rental_type"]),
                               note=body.note or p.get("note"))
    try:
        booking = booking_svc.create_booking(db, booking_in, renter_id=user.id, commit=False)
    except ServiceError as e:
        db.rollback()
        action = _load(db, action_id, user, lock=True)
        action.status, action.result = "failed", {"error": e.detail}
        action.decided_at = datetime.now(timezone.utc)
        db.commit()
        raise
    action.status, action.result = "confirmed", {"booking_id": booking.id, "total_price": booking.total_price}
    action.decided_at = datetime.now(timezone.utc)
    db.commit()  # booking and action status commit together
    return {**_out(action), "booking": {"id": booking.id, "status": booking.status.value,
                                        "total_price": booking.total_price}}


@router.post("/{action_id}/cancel")
def cancel(action_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    action = _load(db, action_id, user, lock=True)
    _ensure_pending(db, action)
    action.status, action.decided_at = "cancelled", datetime.now(timezone.utc)
    db.commit()
    return _out(action)
