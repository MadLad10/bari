import os
import uuid
from typing import Annotated

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from schemas import PropertyCreate, PropertyListOut, PropertyOut, PropertySearchParams, PropertyUpdate
from services import properties as svc

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


@router.get("/{property_id}", response_model=PropertyOut)
def get_property(property_id: int, db: Session = Depends(get_db)):
    return svc.get_property(db, property_id)


@router.post("/", response_model=PropertyOut, status_code=201)
def create_property(payload: PropertyCreate, db: Session = Depends(get_db)):
    return svc.create_property(db, payload)


@router.put("/{property_id}", response_model=PropertyOut)
def update_property(property_id: int, payload: PropertyUpdate, db: Session = Depends(get_db)):
    return svc.update_property(db, property_id, payload)


@router.delete("/{property_id}", status_code=204)
def delete_property(property_id: int, db: Session = Depends(get_db)):
    svc.delete_property(db, property_id)


async def _save_upload(file: UploadFile, allowed: set[str], prefix: str, default_ext: str) -> str:
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else default_ext
    filename = f"{prefix}{uuid.uuid4()}.{ext}"
    async with aiofiles.open(os.path.join(UPLOAD_DIR, filename), "wb") as f:
        await f.write(await file.read())
    return f"/uploads/{filename}"


@router.post("/{property_id}/photos")
async def upload_photo(property_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    svc.get_property(db, property_id)
    url = await _save_upload(file, PHOTO_TYPES, "", "jpg")
    svc.append_file(db, property_id, "photos", url)
    return {"url": url}


@router.post("/{property_id}/documents")
async def upload_document(property_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    svc.get_property(db, property_id)
    url = await _save_upload(file, DOCUMENT_TYPES, "doc_", "pdf")
    svc.append_file(db, property_id, "documents", url)
    return {"url": url, "name": file.filename}
