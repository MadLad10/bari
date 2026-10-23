"""Investigation cases: private reporter feedback and separate admin notes."""
from datetime import datetime, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from services.publication import is_public
from models import CaseUpdate, InvestigationCase, ListingStatus, ModerationDecision, User, UserRole
from rag.indexer import enqueue_index
from services.errors import BadRequest, Conflict, Forbidden, NotFound
from services.properties import get_property
from services.bookings import get_booking
from services.users import ensure_can_view_booking

STATUSES = {"open", "investigating", "awaiting_reporter", "resolved", "dismissed"}
CLOSED = {"resolved", "dismissed"}
TRANSITIONS = {
    "open": {"investigating", "dismissed"},
    "investigating": {"awaiting_reporter", "resolved", "dismissed"},
    "awaiting_reporter": {"investigating", "resolved", "dismissed"},
    "resolved": {"investigating"}, "dismissed": {"investigating"},
}


def get_case(db: Session, case_id: int, user: User, *, lock=False) -> InvestigationCase:
    query = db.query(InvestigationCase).filter_by(id=case_id)
    case = (query.with_for_update().populate_existing() if lock else query).first()
    if not case:
        raise NotFound("Case not found")
    if user.role != UserRole.admin and case.reporter_id != user.id:
        raise Forbidden("This case is private to its reporter and admins")
    return case


def event(db, case, user, kind, body, *, internal=False):
    db.add(CaseUpdate(case_id=case.id, actor_id=user.id if user else case.reporter_id,
                      actor_name=user.name if user else case.reporter_name, kind=kind, internal=internal, body=body))
    case.updated_at = datetime.now(timezone.utc)


def create_case(db: Session, user: User, *, category: str, title: str, description: str,
                property_id=None, booking_id=None, forum_post=None, commit=True) -> InvestigationCase:
    if category == "booking_dispute" and not booking_id:
        raise BadRequest("Select the booking this dispute concerns")
    if category == "unsafe_listing" and not property_id:
        raise BadRequest("Select the listing this safety report concerns")
    prop = get_property(db, property_id) if property_id else None
    if booking_id:
        booking = get_booking(db, booking_id)
        booked_prop = get_property(db, booking.property_id)
        ensure_can_view_booking(user, booking, booked_prop)
        if property_id and property_id != booking.property_id:
            raise BadRequest("This booking belongs to a different property")
        prop = booked_prop
    if prop and not is_public(prop) and not booking_id:
        if user.role != UserRole.admin and prop.owner_id != user.id:
            raise NotFound("Property not found")
    case = InvestigationCase(reporter_id=user.id, reporter_name=user.name, category=category, title=title,
                             description=description, property_id=prop.id if prop else None,
                             property_title=prop.title if prop else None, booking_id=booking_id,
                             booking_reference=booking_id, forum_post_id=forum_post.id if forum_post else None)
    db.add(case); db.flush()
    event(db, case, user, "opened", "Report received. An admin will review your case.")
    if commit:
        db.commit(); db.refresh(case)
    return case


def list_cases(db, user, *, status=None, category=None, q=None, skip=0, limit=30, mine=False):
    query = db.query(InvestigationCase)
    if mine or user.role != UserRole.admin:
        query = query.filter(InvestigationCase.reporter_id == user.id)
    if status:
        query = query.filter(InvestigationCase.status == status)
    if category:
        query = query.filter(InvestigationCase.category == category)
    if q:
        query = query.filter(or_(InvestigationCase.title.ilike(f"%{q}%"),
                                 InvestigationCase.property_title.ilike(f"%{q}%")))
    return query.order_by(InvestigationCase.updated_at.desc(), InvestigationCase.id.desc()).offset(skip).limit(limit).all()


def summary(db, case, *, admin=False):
    assigned = db.get(User, case.assigned_to) if case.assigned_to else None
    data = {key: getattr(case, key) for key in ("id", "category", "title", "description", "status", "property_id",
            "property_title", "booking_id", "booking_reference", "forum_post_id", "resolution", "version",
            "created_at", "updated_at", "resolved_at")}
    data["assigned_name"] = assigned.name if assigned else None
    if admin:
        data.update(reporter_id=case.reporter_id, reporter_name=case.reporter_name, assigned_to=case.assigned_to)
    return data


def detail(db, case, user):
    admin = user.role == UserRole.admin
    query = db.query(CaseUpdate).filter_by(case_id=case.id)
    if not admin:
        query = query.filter_by(internal=False)
    updates = query.order_by(CaseUpdate.created_at, CaseUpdate.id).all()
    data = summary(db, case, admin=admin)
    data["updates"] = [{"id": row.id, "kind": row.kind, "body": row.body, "internal": row.internal,
                         "actor_name": row.actor_name, "created_at": row.created_at} for row in updates]
    data["allowed_statuses"] = sorted(TRANSITIONS[case.status]) if admin else []
    return data


def check_version(case, expected):
    if case.version != expected:
        raise Conflict("This case changed while you were reviewing it. Refresh and review the latest updates.")


def claim(db, case_id, user, expected_version):
    case = get_case(db, case_id, user, lock=True)
    check_version(case, expected_version)
    if case.status in CLOSED:
        raise Conflict("Reopen the case before assigning it")
    case.assigned_to = user.id
    case.version += 1
    event(db, case, user, "assignment", "An admin has taken responsibility for this investigation.")
    db.commit(); db.refresh(case)
    return case


def add_update(db, case_id, user, body, *, internal=False):
    case = get_case(db, case_id, user, lock=True)
    if internal and user.role != UserRole.admin:
        raise Forbidden("Only admins may add investigation notes")
    if case.status in CLOSED:
        raise Conflict("This case is closed. An admin must reopen it before adding updates.")
    event(db, case, user, "note" if internal else "message", body, internal=internal)
    if user.role != UserRole.admin and case.status == "awaiting_reporter":
        case.status = "investigating"
        event(db, case, user, "status", "Your response was received. The case is back under investigation.")
    case.version += 1
    db.commit(); db.refresh(case)
    return case


def decide(db, case_id, user, *, status, message, expected_version, hold_listing=False):
    case = get_case(db, case_id, user, lock=True)
    check_version(case, expected_version)
    if status not in TRANSITIONS[case.status]:
        raise Conflict(f"Cannot change a {case.status} case to {status}")
    if status in CLOSED and len(message.strip()) < 10:
        raise BadRequest("Provide a resolution of at least 10 characters for the reporter")
    if hold_listing:
        if not case.property_id:
            raise BadRequest("This case has no linked listing to hold")
        prop = get_property(db, case.property_id)
        prop.status = ListingStatus.pending
        prop.moderation_reason = f"Listing held for admin investigation (case #{case.id})"
        db.add(ModerationDecision(target_type="listing", target_id=prop.id, workflow="investigation_case",
                                 decision="flag", labels=["investigation"], reasons=[prop.moderation_reason],
                                 signals={"case_id": case.id}))
        enqueue_index(db, "listing", prop.id)
        event(db, case, user, "listing_action", "The linked listing was held for admin review.")
    case.status = status
    case.assigned_to = case.assigned_to or user.id
    case.resolution = message if status in CLOSED else None
    case.resolved_at = datetime.now(timezone.utc) if status in CLOSED else None
    case.version += 1
    event(db, case, user, "resolution" if status in CLOSED else "status", message)
    db.commit(); db.refresh(case)
    return case
