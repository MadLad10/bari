from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import Optional
import aiofiles
import os
import uuid

from config import settings
from database import get_db
from models import Property, ListingStatus, PropertyType, ListingType, RentalType, Furnishing
from schemas import PropertyCreate, PropertyUpdate, PropertyOut, PropertyListOut

router = APIRouter(prefix="/properties", tags=["properties"])

UPLOAD_DIR = settings.upload_dir
os.makedirs(UPLOAD_DIR, exist_ok=True)


def build_filters(
    q, property_type, listing_type, rental_type, furnishing,
    min_price, max_price, bedrooms, area, city,
    nearby_university, max_university_distance_km,
    is_female_only, min_safety_score
):
    filters = [Property.status == ListingStatus.active]

    if q:
        filters.append(
            or_(
                Property.title.ilike(f"%{q}%"),
                Property.description.ilike(f"%{q}%"),
                Property.area.ilike(f"%{q}%"),
                Property.address.ilike(f"%{q}%"),
            )
        )
    if property_type:
        filters.append(Property.property_type == property_type)
    if listing_type:
        filters.append(Property.listing_type == listing_type)
    if rental_type:
        filters.append(Property.rental_type == rental_type)
    if furnishing:
        filters.append(Property.furnishing == furnishing)
    if min_price is not None:
        filters.append(Property.price >= min_price)
    if max_price is not None:
        filters.append(Property.price <= max_price)
    if bedrooms is not None:
        filters.append(Property.bedrooms >= bedrooms)
    if area:
        filters.append(Property.area.ilike(f"%{area}%"))
    if city:
        filters.append(Property.city.ilike(f"%{city}%"))
    if nearby_university:
        filters.append(Property.nearby_university.ilike(f"%{nearby_university}%"))
    if max_university_distance_km is not None:
        filters.append(Property.university_distance_km <= max_university_distance_km)
    if is_female_only is not None:
        filters.append(Property.is_female_only == is_female_only)
    if min_safety_score is not None:
        filters.append(Property.safety_score >= min_safety_score)

    return filters


@router.get("/", response_model=list[PropertyListOut])
def list_properties(
    q: Optional[str] = None,
    property_type: Optional[PropertyType] = None,
    listing_type: Optional[ListingType] = None,
    rental_type: Optional[RentalType] = None,
    furnishing: Optional[Furnishing] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    bedrooms: Optional[int] = None,
    area: Optional[str] = None,
    city: Optional[str] = None,
    nearby_university: Optional[str] = None,
    max_university_distance_km: Optional[float] = None,
    is_female_only: Optional[bool] = None,
    min_safety_score: Optional[float] = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
    db: Session = Depends(get_db),
):
    filters = build_filters(
        q, property_type, listing_type, rental_type, furnishing,
        min_price, max_price, bedrooms, area, city,
        nearby_university, max_university_distance_km,
        is_female_only, min_safety_score
    )
    return (
        db.query(Property)
        .filter(and_(*filters))
        .order_by(Property.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/count")
def count_properties(
    q: Optional[str] = None,
    property_type: Optional[PropertyType] = None,
    listing_type: Optional[ListingType] = None,
    rental_type: Optional[RentalType] = None,
    furnishing: Optional[Furnishing] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    bedrooms: Optional[int] = None,
    area: Optional[str] = None,
    city: Optional[str] = None,
    nearby_university: Optional[str] = None,
    max_university_distance_km: Optional[float] = None,
    is_female_only: Optional[bool] = None,
    min_safety_score: Optional[float] = None,
    db: Session = Depends(get_db),
):
    filters = build_filters(
        q, property_type, listing_type, rental_type, furnishing,
        min_price, max_price, bedrooms, area, city,
        nearby_university, max_university_distance_km,
        is_female_only, min_safety_score
    )
    return {"count": db.query(Property).filter(and_(*filters)).count()}


@router.get("/{property_id}", response_model=PropertyOut)
def get_property(property_id: int, db: Session = Depends(get_db)):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


@router.post("/", response_model=PropertyOut, status_code=201)
def create_property(payload: PropertyCreate, db: Session = Depends(get_db)):
    prop = Property(**payload.model_dump())
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return prop


@router.put("/{property_id}", response_model=PropertyOut)
def update_property(property_id: int, payload: PropertyUpdate, db: Session = Depends(get_db)):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(prop, field, value)
    db.commit()
    db.refresh(prop)
    return prop


@router.delete("/{property_id}", status_code=204)
def delete_property(property_id: int, db: Session = Depends(get_db)):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    db.delete(prop)
    db.commit()


@router.post("/{property_id}/photos")
async def upload_photo(property_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    allowed = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, or WebP images allowed")

    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "jpg"
    filename = f"{uuid.uuid4()}.{ext}"
    path = os.path.join(UPLOAD_DIR, filename)

    async with aiofiles.open(path, "wb") as f:
        content = await file.read()
        await f.write(content)

    photos = list(prop.photos or [])
    photos.append(f"/uploads/{filename}")
    prop.photos = photos
    db.commit()

    return {"url": f"/uploads/{filename}"}


@router.post("/{property_id}/documents")
async def upload_document(property_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    allowed = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only PDF, JPEG, PNG, or WebP files allowed")

    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "pdf"
    filename = f"doc_{uuid.uuid4()}.{ext}"
    path = os.path.join(UPLOAD_DIR, filename)

    async with aiofiles.open(path, "wb") as f:
        content = await file.read()
        await f.write(content)

    documents = list(prop.documents or [])
    documents.append(f"/uploads/{filename}")
    prop.documents = documents
    db.commit()

    return {"url": f"/uploads/{filename}", "name": file.filename}
