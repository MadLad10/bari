from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import BookingStatus, RentalType
from services import bookings as svc
from services.bookings import BookingCreate

router = APIRouter(prefix="/bookings", tags=["bookings"])


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
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("/", response_model=BookingOut, status_code=201)
def create_booking(payload: BookingCreate, db: Session = Depends(get_db)):
    return svc.create_booking(db, payload)


@router.get("/property/{property_id}", response_model=list[BookingOut])
def get_property_bookings(property_id: int, db: Session = Depends(get_db)):
    return svc.list_property_bookings(db, property_id)


@router.get("/property/{property_id}/availability")
def get_availability(property_id: int, db: Session = Depends(get_db)):
    return [
        {"check_in": b.check_in.isoformat(), "check_out": b.check_out.isoformat(), "status": b.status}
        for b in svc.upcoming_bookings(db, property_id)
    ]


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: int, db: Session = Depends(get_db)):
    return svc.get_booking(db, booking_id)


@router.patch("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(booking_id: int, db: Session = Depends(get_db)):
    return svc.cancel_booking(db, booking_id)
