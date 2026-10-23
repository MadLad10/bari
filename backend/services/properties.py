from sqlalchemy import and_, or_, text
from sqlalchemy.orm import Session

from datetime import datetime, timezone

from models import Booking, BookingStatus, Document, ListingStatus, ListingType, Property, PropertyDocument, SafetyVote
from jobs.queue import enqueue
from rag.indexer import enqueue_index
from schemas import PropertyCreate, PropertySearchParams, PropertyUpdate
from services.errors import Conflict, NotFound
from services.publication import public_filter


def build_filters(params: PropertySearchParams) -> list:
    filters = [public_filter()]

    if params.q:
        q = params.q
        filters.append(
            or_(
                Property.title.ilike(f"%{q}%"),
                Property.description.ilike(f"%{q}%"),
                Property.area.ilike(f"%{q}%"),
                Property.address.ilike(f"%{q}%"),
            )
        )
    if params.property_type:
        filters.append(Property.property_type == params.property_type)
    if params.listing_type:
        filters.append(Property.listing_type == params.listing_type)
    if params.rental_type:
        filters.append(Property.rental_type == params.rental_type)
    if params.furnishing:
        filters.append(Property.furnishing == params.furnishing)
    if params.min_price is not None:
        filters.append(Property.price >= params.min_price)
    if params.max_price is not None:
        filters.append(Property.price <= params.max_price)
    if params.bedrooms is not None:
        filters.append(Property.bedrooms >= params.bedrooms)
    if params.area:
        filters.append(Property.area.ilike(f"%{params.area}%"))
    if params.city:
        filters.append(Property.city.ilike(f"%{params.city}%"))
    if params.nearby_university:
        filters.append(Property.nearby_university.ilike(f"%{params.nearby_university}%"))
    if params.max_university_distance_km is not None:
        filters.append(Property.university_distance_km <= params.max_university_distance_km)
    if params.is_female_only is not None:
        filters.append(Property.is_female_only == params.is_female_only)
    if params.min_safety_score is not None:
        filters.append(Property.safety_score >= params.min_safety_score)

    return filters


def search_properties(db: Session, params: PropertySearchParams) -> list[Property]:
    return (
        db.query(Property)
        .filter(and_(*build_filters(params)))
        .order_by(Property.created_at.desc(), Property.id.desc())
        .offset(params.skip)
        .limit(params.limit)
        .all()
    )


def count_properties(db: Session, params: PropertySearchParams) -> int:
    return db.query(Property).filter(and_(*build_filters(params))).count()


PUBLIC_SUMMARY_FIELDS = ("id", "title", "area", "price", "rental_type", "bedrooms", "property_type", "listing_type",
                         "furnishing", "is_female_only", "women_safety_status", "safety_score", "nearby_university",
                         "university_distance_km", "photos")


def public_summary(p: Property) -> dict:
    """Public listing fields for search results and the agent. Owner phone/email are deliberately excluded."""
    return {f: getattr(getattr(p, f), "value", getattr(p, f)) for f in PUBLIC_SUMMARY_FIELDS}


def get_property(db: Session, property_id: int) -> Property:
    prop = db.get(Property, property_id)
    if not prop:
        raise NotFound("Property not found")
    return prop


def normalize_area(db: Session, raw: str | None, min_similarity: float = 0.3) -> str | None:
    """Map a free-text area ("Boshundhara", "mirpur 10") to a known area name with pg_trgm similarity.

    Returns the input unchanged when it already matches, or when nothing is similar enough."""
    if not raw or not raw.strip():
        return raw
    if db.query(Property.id).filter(Property.area.ilike(f"%{raw.strip()}%")).first():
        return raw
    row = db.execute(text(
        "SELECT area, similarity(area, :q) AS s FROM (SELECT DISTINCT area FROM properties) a "
        "ORDER BY s DESC LIMIT 1"), {"q": raw.strip()}).first()
    return row.area if row and row.s >= min_similarity else raw


def owner_properties(db: Session, owner_id: int) -> list[Property]:
    return db.query(Property).filter(Property.owner_id == owner_id).order_by(Property.created_at.desc()).all()


def get_properties(db: Session, ids: list[int]) -> list[Property]:
    return db.query(Property).filter(Property.id.in_(ids)).all() if ids else []


def create_property(db: Session, payload: PropertyCreate, **extra) -> Property:
    prop = Property(**payload.model_dump(), status=ListingStatus.pending, **extra)
    db.add(prop)
    db.flush()
    enqueue_index(db, "listing", prop.id)  # committed atomically with the listing (outbox)
    enqueue(db, "screen_listing", {"property_id": prop.id}, dedupe_key=f"screen:{prop.id}")
    db.commit()
    db.refresh(prop)
    return prop


def update_property(db: Session, property_id: int, payload: PropertyUpdate) -> Property:
    from services import women_safety
    prop = women_safety.locked(db, property_id)
    changes = {key: value for key, value in payload.model_dump(exclude_unset=True).items()
               if getattr(prop, key) != value}
    if changes.get("listing_type", prop.listing_type) == ListingType.sale:
        changes["rental_type"] = None
    for field, value in changes.items():
        setattr(prop, field, value)
    if women_safety.REVIEW_FIELDS & changes.keys():
        women_safety.invalidate(db, prop)
    if {"owner_name", "address", "area", "city"} & changes.keys():
        from services.verification import invalidate
        invalidate(db, prop)
    enqueue_index(db, "listing", prop.id)
    if {"title", "description", "price"} & changes.keys():  # scams are often edited in after approval
        enqueue(db, "screen_listing", {"property_id": prop.id}, dedupe_key=f"screen:{prop.id}")
    if {"title", "status"} & changes.keys():  # safety chunks quote the title and vanish with inactive listings
        for (vote_id,) in db.query(SafetyVote.id).filter(SafetyVote.property_id == prop.id,
                                                        SafetyVote.comment.isnot(None)):
            enqueue_index(db, "safety", vote_id)
    db.commit()
    db.refresh(prop)
    return prop


def delete_property(db: Session, property_id: int) -> None:
    prop = get_property(db, property_id)
    db.refresh(prop, with_for_update=True)
    if db.query(Booking.id).filter(Booking.property_id == property_id,
                                 Booking.status != BookingStatus.cancelled,
                                 Booking.check_out > datetime.now(timezone.utc)).first():
        raise Conflict("Resolve upcoming bookings before deleting this listing. You can pause it instead.")
    stored = [d.stored_name for d in db.query(PropertyDocument).filter_by(property_id=property_id)]
    db.query(Document).filter(Document.property_id == property_id,
                              Document.source_type.in_(("listing", "safety"))).delete(synchronize_session=False)
    db.delete(prop)
    db.commit()
    from services.verification import private_path
    for name in stored:
        private_path(name).unlink(missing_ok=True)


def append_file(db: Session, property_id: int, field: str, url: str) -> Property:
    """Append an uploaded file URL to the `photos` or `documents` list."""
    from services import women_safety
    prop = women_safety.locked(db, property_id)
    setattr(prop, field, [*(getattr(prop, field) or []), url])
    if field == "photos":
        women_safety.invalidate(db, prop)
    db.commit()
    return prop
