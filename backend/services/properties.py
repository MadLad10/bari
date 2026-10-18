from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from models import Document, ListingStatus, Property, SafetyVote
from rag.indexer import enqueue_index
from schemas import PropertyCreate, PropertySearchParams, PropertyUpdate
from services.errors import NotFound


def build_filters(params: PropertySearchParams) -> list:
    filters = [Property.status == ListingStatus.active]

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
                         "furnishing", "is_female_only", "safety_score", "nearby_university",
                         "university_distance_km", "photos")


def public_summary(p: Property) -> dict:
    """Public listing fields for search results and the agent. Owner phone/email are deliberately excluded."""
    return {f: getattr(getattr(p, f), "value", getattr(p, f)) for f in PUBLIC_SUMMARY_FIELDS}


def get_property(db: Session, property_id: int) -> Property:
    prop = db.get(Property, property_id)
    if not prop:
        raise NotFound("Property not found")
    return prop


def get_properties(db: Session, ids: list[int]) -> list[Property]:
    return db.query(Property).filter(Property.id.in_(ids)).all() if ids else []


def create_property(db: Session, payload: PropertyCreate, **extra) -> Property:
    prop = Property(**payload.model_dump(), **extra)
    db.add(prop)
    db.flush()
    enqueue_index(db, "listing", prop.id)  # committed atomically with the listing (outbox)
    db.commit()
    db.refresh(prop)
    return prop


def update_property(db: Session, property_id: int, payload: PropertyUpdate) -> Property:
    prop = get_property(db, property_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(prop, field, value)
    enqueue_index(db, "listing", prop.id)
    if {"title", "status"} & changes.keys():  # safety chunks quote the title and vanish with inactive listings
        for (vote_id,) in db.query(SafetyVote.id).filter(SafetyVote.property_id == prop.id,
                                                        SafetyVote.comment.isnot(None)):
            enqueue_index(db, "safety", vote_id)
    db.commit()
    db.refresh(prop)
    return prop


def delete_property(db: Session, property_id: int) -> None:
    prop = get_property(db, property_id)
    db.query(Document).filter(Document.property_id == property_id,
                              Document.source_type.in_(("listing", "safety"))).delete(synchronize_session=False)
    db.delete(prop)
    db.commit()


def append_file(db: Session, property_id: int, field: str, url: str) -> Property:
    """Append an uploaded file URL to the `photos` or `documents` list."""
    prop = get_property(db, property_id)
    setattr(prop, field, [*(getattr(prop, field) or []), url])
    db.commit()
    return prop
