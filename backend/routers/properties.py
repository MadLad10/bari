import os
import uuid
from typing import Annotated
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from deps import get_current_user, get_current_user_optional, require_role
from models import InvestigationCase, ListingStatus, PropertyDocument, User, UserRole
from services.errors import BadRequest, Forbidden, NotFound
from schemas import PropertyCreate, PropertyListOut, PropertyOut, PropertyPublicOut, PropertySearchParams, PropertyUpdate
from services import properties as svc
from services import verification
from services.publication import is_public, safety_ready
from services.users import ensure_can_manage_property

router = APIRouter(prefix="/properties", tags=["properties"])

UPLOAD_DIR = settings.upload_dir
os.makedirs(UPLOAD_DIR, exist_ok=True)

PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
DOCUMENT_TYPES = {"application/pdf", *PHOTO_TYPES}


@router.get("/", response_model=list[PropertyListOut])
def list_properties(params: Annotated[PropertySearchParams, Query()], db: Session = Depends(get_db)):
    return svc.search_properties(db, params)


@router.get("/count")
def count_properties(params: Annotated[PropertySearchParams, Query()], db: Session = Depends(get_db)):
    return {"count": svc.count_properties(db, params)}


@router.get("/map")
def map_properties(params: Annotated[PropertySearchParams, Query()], db: Session = Depends(get_db)):
    from models import Property
    query = db.query(Property).filter(*svc.build_filters(params))
    total = query.count()
    located = query.filter(Property.latitude.isnot(None), Property.longitude.isnot(None))
    mapped = located.count()
    rows = located.order_by(Property.id).limit(1000).all()
    return {"total": total, "located": mapped, "missing_coordinates": total - mapped,
            "truncated": mapped > len(rows), "items": [{"id": p.id, "title": p.title, "area": p.area,
                "latitude": p.latitude, "longitude": p.longitude, "price": p.price,
                "listing_type": p.listing_type.value, "rental_type": p.rental_type.value if p.rental_type else None} for p in rows]}


@router.get("/mine")
def my_properties(db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.owner))):
    """The owner's own listings, including ones held for review and why."""
    return [{**PropertyOut.model_validate(p).model_dump(mode="json"), "moderation_reason": p.moderation_reason}
            for p in svc.owner_properties(db, user.id)]


@router.get("/{property_id}", response_model=PropertyPublicOut)
def get_property(property_id: int, db: Session = Depends(get_db),
                 user: User | None = Depends(get_current_user_optional)):
    prop = svc.get_property(db, property_id)
    if not is_public(prop) and (user is None or (user.id != prop.owner_id and user.role != UserRole.admin)):
        raise NotFound("Property not found")
    return prop


@router.post("/", response_model=PropertyOut, status_code=201)
def create_property(payload: PropertyCreate, db: Session = Depends(get_db),
                    user: User = Depends(require_role(UserRole.owner))):
    return svc.create_property(db, payload, owner_id=user.id)


def _managed_property(db: Session, property_id: int, user: User):
    prop = svc.get_property(db, property_id)
    ensure_can_manage_property(user, prop)
    return prop


@router.put("/{property_id}", response_model=PropertyOut)
def update_property(property_id: int, payload: PropertyUpdate, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    prop = _managed_property(db, property_id, user)
    db.refresh(prop, with_for_update=True)
    if prop.archived_at is not None:
        raise NotFound("Property not found")
    if payload.photos is not None and any(photo not in (prop.photos or []) for photo in payload.photos):
        raise BadRequest("Add new photos through the photo upload endpoint")
    if payload.status == ListingStatus.active:
        if (payload.is_female_only if payload.is_female_only is not None else prop.is_female_only) and not safety_ready(prop):
            raise Forbidden("Separate admin safety approval is required for women-only accommodation")
        if prop.status != ListingStatus.active and db.query(InvestigationCase.id).filter(
                InvestigationCase.property_id == property_id,
                InvestigationCase.status.in_(["open", "investigating", "awaiting_reporter"])).first():
            raise Forbidden("Resolve open investigations about this listing before publishing it")
        if prop.document_check_status not in ("passed", "reviewed"):
            raise Forbidden("Document checks must pass before this listing can be published")
        if prop.moderation_reason and user.role != UserRole.admin:
            raise Forbidden("This listing needs moderator approval before publication")
    if (payload.status is not None and prop.status == ListingStatus.pending and prop.moderation_reason
            and user.role != UserRole.admin):
        raise Forbidden("This listing is under review by bari moderators")
    return svc.update_property(db, property_id, payload)


@router.delete("/{property_id}", status_code=204)
def delete_property(property_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _managed_property(db, property_id, user)
    svc.delete_property(db, property_id)


async def _save_upload(file: UploadFile, allowed: set[str], prefix: str, default_ext: str) -> str:
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}[file.content_type]
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise BadRequest("Each photo must be under 10 MB")
    filename = f"{prefix}{uuid.uuid4()}.{ext}"
    async with aiofiles.open(os.path.join(UPLOAD_DIR, filename), "wb") as f:
        await f.write(data)
    return f"/uploads/{filename}"


@router.post("/{property_id}/photos")
async def upload_photo(property_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    _managed_property(db, property_id, user)
    url = await _save_upload(file, PHOTO_TYPES, "", "jpg")
    svc.append_file(db, property_id, "photos", url)
    return {"url": url}


@router.post("/{property_id}/documents")
async def upload_document(property_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    prop = _managed_property(db, property_id, user)
    data = await file.read(verification.MAX_BYTES + 1)
    doc = verification.register_document(db, prop, data, file.content_type, file.filename or "document")
    return {"id": doc.id, "url": f"/api/properties/{property_id}/documents/{doc.id}",
            "name": doc.original_name, "status": prop.document_check_status}


@router.get("/{property_id}/verification")
def get_verification(property_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return verification.summary(db, _managed_property(db, property_id, user))


@router.get("/{property_id}/documents/legacy/{filename}")
def download_legacy_document(property_id: int, filename: str, db: Session = Depends(get_db),
                             user: User = Depends(get_current_user)):
    prop = _managed_property(db, property_id, user)
    if Path(filename).name != filename or f"/uploads/{filename}" not in (prop.documents or []):
        raise NotFound("Document not found")
    root = Path(UPLOAD_DIR).resolve()
    path = (root / filename).resolve()
    if path.parent != root or not path.is_file():
        raise NotFound("Document not found")
    return FileResponse(path, filename=filename, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


def _document(db, property_id: int, document_id: int):
    doc = db.get(PropertyDocument, document_id)
    if not doc or doc.property_id != property_id:
        raise NotFound("Document not found")
    return doc


@router.get("/{property_id}/documents/{document_id}")
def download_document(property_id: int, document_id: int, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    _managed_property(db, property_id, user)
    doc = _document(db, property_id, document_id)
    path = verification.private_path(doc.stored_name)
    if not path.is_file():
        raise NotFound("Document not found")
    return FileResponse(path, filename=doc.original_name, media_type=doc.content_type,
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.delete("/{property_id}/documents/{document_id}", status_code=204)
def remove_document(property_id: int, document_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    prop = _managed_property(db, property_id, user)
    verification.remove_document(db, prop, _document(db, property_id, document_id))
