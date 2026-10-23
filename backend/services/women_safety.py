"""Owner requests and independent, auditable admin safety decisions."""
from datetime import datetime, timezone

from models import InvestigationCase, ListingStatus, Property, UserRole, WomenSafetyReview, SafetyVote
from rag.indexer import enqueue_index
from services.errors import BadRequest, Conflict, Forbidden, NotFound
from services.users import ensure_can_manage_property

OWNER_CHECKS = ("women_only_policy", "secure_access", "common_area_lighting", "privacy", "emergency_contact")
ADMIN_CHECKS = ("identity_and_documents", "access_and_lighting", "occupancy_and_privacy", "emergency_arrangements", "evidence_reviewed")
REVIEW_FIELDS = {"title", "description", "owner_name", "owner_phone", "owner_email", "address", "area", "city",
                 "property_type", "listing_type", "bedrooms", "bathrooms", "amenities", "photos", "is_female_only"}


def locked(db, property_id):
    prop = db.query(Property).filter_by(id=property_id).with_for_update().populate_existing().first()
    if not prop:
        raise NotFound("Property not found")
    return prop


def reindex(db, prop):
    enqueue_index(db, "listing", prop.id)
    for (vote_id,) in db.query(SafetyVote.id).filter_by(property_id=prop.id):
        enqueue_index(db, "safety", vote_id)


def invalidate(db, prop):
    prop.women_safety_version += 1
    prop.women_safety_status = "not_submitted"
    prop.women_safety_submission = {}
    prop.women_safety_feedback = "Listing or supporting evidence changed. Submit a fresh safety review request."
    prop.women_safety_reviewed_at = None
    if prop.is_female_only and prop.status == ListingStatus.active:
        prop.status = ListingStatus.pending
    reindex(db, prop)


def summary(db, prop):
    from services.verification import summary as document_summary
    history = db.query(WomenSafetyReview).filter_by(property_id=prop.id).order_by(WomenSafetyReview.id.desc()).all()
    return {"property_id": prop.id, "title": prop.title, "address": prop.address, "area": prop.area,
            "owner_id": prop.owner_id, "is_female_only": prop.is_female_only,
            "status": prop.women_safety_status, "version": prop.women_safety_version,
            "submission": prop.women_safety_submission, "feedback": prop.women_safety_feedback,
            "reviewed_at": prop.women_safety_reviewed_at, "listing_status": prop.status.value,
            "document_check_status": prop.document_check_status, "moderation_reason": prop.moderation_reason,
            "description": prop.description, "photos": prop.photos, "owner_name": prop.owner_name,
            "documents": document_summary(db, prop)["documents"],
            "history": [{"id": r.id, "verdict": r.verdict, "reviewer": r.reviewer_name, "version": r.version,
                         "checklist": r.checklist, "submission": r.submission, "notes": r.notes,
                         "created_at": r.created_at} for r in history]}


def check_version(prop, version):
    if prop.women_safety_version != version:
        raise Conflict("This listing or review changed. Refresh before continuing.")


def submit(db, property_id, payload, user):
    prop = locked(db, property_id)
    ensure_can_manage_property(user, prop)
    if user.id != prop.owner_id:
        raise Forbidden("Only the listing owner can submit a safety request")
    if not prop.is_female_only:
        raise BadRequest("Select women-only accommodation in listing details first")
    check_version(prop, payload.expected_version)
    if prop.women_safety_status in ("pending", "approved"):
        raise BadRequest("This request is already pending or approved")
    if not all(payload.checklist.get(k) is True for k in OWNER_CHECKS):
        raise BadRequest("Confirm every safety requirement before submitting")
    prop.women_safety_version += 1
    prop.women_safety_status = "pending"
    prop.women_safety_submission = {"checklist": {k: True for k in OWNER_CHECKS}, "notes": payload.notes,
                                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                                    "listing_snapshot": {k: getattr(getattr(prop, k), "value", getattr(prop, k))
                                                         for k in REVIEW_FIELDS}}
    prop.women_safety_feedback = None
    prop.women_safety_reviewed_at = None
    if prop.status == ListingStatus.active:
        prop.status = ListingStatus.pending
    reindex(db, prop)
    db.commit()
    return summary(db, prop)


def decide(db, property_id, payload, admin):
    prop = locked(db, property_id)
    check_version(prop, payload.expected_version)
    if prop.owner_id == admin.id:
        raise Forbidden("Another admin must independently review your listing")
    if not prop.is_female_only:
        raise BadRequest("This listing is not requesting women-only approval")
    if payload.verdict == "approved":
        if prop.women_safety_status != "pending":
            raise BadRequest("A current owner safety request is required")
        if not all(payload.checklist.get(k) is True for k in ADMIN_CHECKS):
            raise BadRequest("Complete every admin safety check before approval")
        if prop.document_check_status not in ("passed", "reviewed"):
            raise BadRequest("Complete the separate ownership document checks first")
        if prop.moderation_reason or db.query(InvestigationCase.id).filter(
                InvestigationCase.property_id == prop.id,
                InvestigationCase.status.in_(("open", "investigating", "awaiting_reporter"))).first():
            raise BadRequest("Resolve moderation holds and open investigations before approval")
    elif prop.women_safety_status not in ("pending", "approved"):
        raise BadRequest("Only pending or approved requests can be reviewed")
    db.add(WomenSafetyReview(property_id=prop.id, reviewer_id=admin.id, reviewer_name=admin.name,
                            verdict=payload.verdict, version=prop.women_safety_version,
                            checklist={k: payload.checklist.get(k, False) for k in ADMIN_CHECKS},
                            submission=prop.women_safety_submission, notes=payload.notes))
    prop.women_safety_status = payload.verdict
    prop.women_safety_version += 1
    prop.women_safety_feedback = payload.notes
    prop.women_safety_reviewed_at = datetime.now(timezone.utc)
    # Preserve an owner's explicit pause. Review does not clear independent holds.
    if payload.verdict == "approved" and prop.status == ListingStatus.pending:
        prop.status = ListingStatus.active
    elif payload.verdict != "approved" and prop.status == ListingStatus.active:
        prop.status = ListingStatus.pending
    reindex(db, prop)
    db.commit()
    return summary(db, prop)
