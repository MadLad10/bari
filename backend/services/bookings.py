from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models import Booking, BookingStatus, ListingStatus, Property, RentalType
from services.errors import BadRequest, Conflict, NotFound
from services.properties import get_property


class BookingCreate(BaseModel):
    property_id: int
    renter_name: str = Field(..., min_length=2)
    renter_phone: str = Field(..., min_length=11)
    renter_email: str | None = None
    check_in: datetime
    check_out: datetime
    rental_type: RentalType
    note: str | None = None


def compute_price(prop: Property, check_in: datetime, check_out: datetime, rental_type: RentalType) -> float:
    delta = check_out - check_in
    if rental_type == RentalType.hourly:
        hours = max(delta.total_seconds() / 3600, 1)
        return round(prop.price * hours, 2)
    if rental_type == RentalType.daily:
        days = max(delta.days, 1)
        return round(prop.price * days, 2)
    # monthly: count started months
    months = max(round(delta.days / 30), 1)
    return round(prop.price * months, 2)


def overlapping_bookings(db: Session, property_id: int, check_in: datetime, check_out: datetime,
                         exclude_id: int | None = None) -> list[Booking]:
    q = db.query(Booking).filter(
        Booking.property_id == property_id,
        Booking.status != BookingStatus.cancelled,
        Booking.check_in < check_out,
        Booking.check_out > check_in,
    )
    if exclude_id:
        q = q.filter(Booking.id != exclude_id)
    return q.all()


def has_overlap(db: Session, property_id: int, check_in: datetime, check_out: datetime,
                exclude_id: int | None = None) -> bool:
    return bool(overlapping_bookings(db, property_id, check_in, check_out, exclude_id))


def validate_booking(db: Session, property_id: int, check_in: datetime, check_out: datetime,
                     rental_type: RentalType) -> tuple[Property, float]:
    """All checks that must pass before a booking can exist. Returns the property and total price.

    Shared by the booking endpoint, the agent's draft_booking tool and the confirm endpoint."""
    if check_out <= check_in:
        raise BadRequest("check_out must be after check_in")
    prop = get_property(db, property_id)
    if prop.status != ListingStatus.active:
        raise Conflict("This listing is not available for booking")
    if has_overlap(db, property_id, check_in, check_out):
        raise Conflict("Property is already booked for the selected dates")
    return prop, compute_price(prop, check_in, check_out, rental_type)


def create_booking(db: Session, payload: BookingCreate, *, commit: bool = True, **extra) -> Booking:
    _, total = validate_booking(db, payload.property_id, payload.check_in, payload.check_out, payload.rental_type)
    booking = Booking(**payload.model_dump(), total_price=total, **extra)
    db.add(booking)
    if commit:
        db.commit()
        db.refresh(booking)
    else:
        db.flush()
    return booking


def list_property_bookings(db: Session, property_id: int) -> list[Booking]:
    return (
        db.query(Booking)
        .filter(Booking.property_id == property_id, Booking.status != BookingStatus.cancelled)
        .order_by(Booking.check_in)
        .all()
    )


def list_user_bookings(db: Session, user_id: int) -> list[Booking]:
    return db.query(Booking).filter(Booking.renter_id == user_id).order_by(Booking.created_at.desc()).all()


def upcoming_bookings(db: Session, property_id: int) -> list[Booking]:
    return (
        db.query(Booking)
        .filter(
            Booking.property_id == property_id,
            Booking.status != BookingStatus.cancelled,
            Booking.check_out >= datetime.now(timezone.utc),
        )
        .order_by(Booking.check_in)
        .all()
    )


def get_booking(db: Session, booking_id: int) -> Booking:
    b = db.get(Booking, booking_id)
    if not b:
        raise NotFound("Booking not found")
    return b


def cancel_booking(db: Session, booking_id: int) -> Booking:
    b = get_booking(db, booking_id)
    if b.status == BookingStatus.cancelled:
        raise BadRequest("Booking is already cancelled")
    b.status = BookingStatus.cancelled
    db.commit()
    db.refresh(b)
    return b
