"""Shared visibility policy; does not import indexing or workflow services."""
from sqlalchemy import and_, or_
from models import ListingStatus, Property


def safety_ready(prop):
    return not prop.is_female_only or (prop.women_safety_status == "approved"
                                      and prop.document_check_status in ("passed", "reviewed"))


def is_public(prop):
    return prop.status == ListingStatus.active and safety_ready(prop)


def public_filter():
    return and_(Property.status == ListingStatus.active,
                or_(Property.is_female_only.is_(False),
                    and_(Property.women_safety_status == "approved",
                         Property.document_check_status.in_(("passed", "reviewed")))))
