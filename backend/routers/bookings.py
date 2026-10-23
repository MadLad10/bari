from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from deps import get_current_user, require_role
from models import BookingStatus, ListingStatus, RentalType, User, UserRole
from services import bookings as svc
from services.bookings import BookingCreate
from services.properties import get_property
from services.users import ensure_can_cancel_booking, ensure_can_manage_property, ensure_can_view_booking

router = APIRouter(prefix="/bookings", tags=["bookings"])


class BookedPropertyOut(BaseModel):
    id: int
    title: str
    address: str
    area: str
    city: str
    photos: list[str] = []
    status: ListingStatus
    owner_name: str

    model_config = {"from_attributes": True}


class BookingOut(BaseModel):
    id: int
    property_id: int
    renter_name: str
    renter_phone: str
    renter_email: str | None
    check_in: datetime
    check_out: datetime
    rental_type: RentalType
    total_price: float
    status: BookingStatus
    cancellation_reason: str | None = None
    cancelled_at: datetime | None = None
    property: BookedPropertyOut | None = None
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class BookingQuoteIn(BaseModel):
    property_id: int
    check_in: datetime
    check_out: datetime
    rental_type: RentalType


@router.post("/quote")
def quote_booking(payload: BookingQuoteIn, db: Session = Depends(get_db)):
    _, total = svc.validate_booking(db, **payload.model_dump())
    return {"total_price": total, "currency": "BDT"}


@router.post("/", response_model=BookingOut, status_code=201)
def create_booking(payload: BookingCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.create_booking(db, payload, renter_id=user.id)


@router.get("/mine", response_model=list[BookingOut])
def my_bookings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.list_user_bookings(db, user.id)


@router.get("/owner", response_model=list[BookingOut])
def owner_bookings(db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.owner))):
    return svc.owner_bookings(db, user.id)


@router.get("/property/{property_id}", response_model=list[BookingOut])
def get_property_bookings(property_id: int, db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    # Includes renter contact details, so only the listing owner (or an admin) may see it.
    ensure_can_manage_property(user, get_property(db, property_id))
    return svc.list_property_bookings(db, property_id)


@router.get("/property/{property_id}/availability")
def get_availability(property_id: int, db: Session = Depends(get_db)):
    return [
        {"check_in": b.check_in.isoformat(), "check_out": b.check_out.isoformat(), "status": b.status}
        for b in svc.upcoming_bookings(db, property_id)
    ]


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    b = svc.get_booking(db, booking_id)
    ensure_can_view_booking(user, b, get_property(db, b.property_id))
    return b


@router.patch("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    b = svc.get_booking(db, booking_id)
    ensure_can_cancel_booking(user, b, get_property(db, b.property_id))
    return svc.cancel_booking(db, booking_id, actor=user)


@router.patch("/{booking_id}/accept", response_model=BookingOut)
def accept_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    b = svc.get_booking(db, booking_id)
    ensure_can_manage_property(user, get_property(db, b.property_id))
    return svc.decide_booking(db, booking_id, accept=True)


@router.patch("/{booking_id}/decline", response_model=BookingOut)
def decline_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    b = svc.get_booking(db, booking_id)
    ensure_can_manage_property(user, get_property(db, b.property_id))
    return svc.decide_booking(db, booking_id, accept=False)
