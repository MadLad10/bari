"""Only registered property photos may be served publicly, including for legacy uploads."""
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Property
from services.errors import NotFound

router = APIRouter()


@router.get("/uploads/{filename}")
def photo(filename: str, db: Session = Depends(get_db)):
    url = f"/uploads/{filename}"
    if (Path(filename).name != filename or filename.startswith("doc_")
            or db.query(Property.id).filter(Property.documents.contains([url])).first()
            or not db.query(Property.id).filter(Property.photos.contains([url])).first()):
        raise NotFound("Photo not found")
    root = Path(settings.upload_dir).resolve()
    path = (root / filename).resolve()
    if path.parent != root or not path.is_file():
        raise NotFound("Photo not found")
    return FileResponse(path, headers={"X-Content-Type-Options": "nosniff"})
