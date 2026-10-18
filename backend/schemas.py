from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from models import PropertyType, ListingType, RentalType, Furnishing, ListingStatus


class PropertyBase(BaseModel):
    title: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=20)
    property_type: PropertyType
    listing_type: ListingType
    rental_type: Optional[RentalType] = None
    furnishing: Furnishing
    price: float = Field(..., gt=0)
    bedrooms: int = Field(default=1, ge=0)
    bathrooms: int = Field(default=1, ge=0)
    area_sqft: Optional[float] = None
    address: str = Field(..., min_length=5)
    area: str = Field(..., min_length=2)
    city: str = "Dhaka"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    nearby_university: Optional[str] = None
    university_distance_km: Optional[float] = None
    is_female_only: bool = False
    safety_score: Optional[float] = Field(default=None, ge=0, le=5)
    amenities: list[str] = []
    photos: list[str] = []
    documents: list[str] = []
    has_furniture_for_sale: bool = False
    owner_name: str = Field(..., min_length=2)
    owner_phone: str = Field(..., min_length=11)
    owner_email: Optional[EmailStr] = None


class PropertyCreate(PropertyBase):
    pass


class PropertyUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    furnishing: Optional[Furnishing] = None
    rental_type: Optional[RentalType] = None
    is_female_only: Optional[bool] = None
    safety_score: Optional[float] = None
    amenities: Optional[list[str]] = None
    photos: Optional[list[str]] = None
    documents: Optional[list[str]] = None
    has_furniture_for_sale: Optional[bool] = None
    status: Optional[ListingStatus] = None


class PropertyOut(PropertyBase):
    id: int
    status: ListingStatus
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PropertyListOut(BaseModel):
    id: int
    title: str
    property_type: PropertyType
    listing_type: ListingType
    rental_type: Optional[RentalType] = None
    furnishing: Furnishing
    price: float
    bedrooms: int
    bathrooms: int
    area: str
    city: str
    nearby_university: Optional[str] = None
    university_distance_km: Optional[float] = None
    is_female_only: bool
    safety_score: Optional[float] = None
    photos: list[str] = []
    status: ListingStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class PropertySearchParams(BaseModel):
    q: Optional[str] = None
    property_type: Optional[PropertyType] = None
    listing_type: Optional[ListingType] = None
    rental_type: Optional[RentalType] = None
    furnishing: Optional[Furnishing] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    bedrooms: Optional[int] = None
    area: Optional[str] = None
    city: Optional[str] = None
    nearby_university: Optional[str] = None
    max_university_distance_km: Optional[float] = None
    is_female_only: Optional[bool] = None
    min_safety_score: Optional[float] = None
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
