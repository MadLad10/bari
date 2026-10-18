from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from deps import require_role
from llm.context import request_id_var
from models import Furnishing, ListingType, PropertyType, RentalType, User, UserRole
from workflows.listing_assistant import assist

router = APIRouter(prefix="/listing-assistant", tags=["listing assistant"])


class DraftListing(BaseModel):
    """Everything optional: the assistant works on a half-filled form."""
    title: str | None = None
    description: str | None = None
    property_type: PropertyType | None = None
    listing_type: ListingType | None = None
    rental_type: RentalType | None = None
    furnishing: Furnishing | None = None
    price: float | None = Field(None, ge=0)
    bedrooms: int | None = Field(None, ge=0)
    bathrooms: int | None = Field(None, ge=0)
    area_sqft: float | None = None
    address: str | None = None
    area: str | None = None
    nearby_university: str | None = None
    university_distance_km: float | None = None
    is_female_only: bool | None = None
    amenities: list[str] = []
    photos: list[str] = []
    has_furniture_for_sale: bool | None = None
    language: Literal["en", "bn"] = "en"


@router.post("")
def listing_assistant(draft: DraftListing, db: Session = Depends(get_db),
                      _: User = Depends(require_role(UserRole.owner))):
    fields = draft.model_dump(mode="json", exclude={"language"})
    return assist(db, fields, language=draft.language, request_id=request_id_var.get())
