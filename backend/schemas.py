from pydantic import BaseModel, Field, EmailStr, field_validator, model_validator
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
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
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
    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Supply both latitude and longitude, or leave both empty")
        return self

    @field_validator("documents")
    @classmethod
    def uploaded_documents_only(cls, value):
        if value:
            raise ValueError("Upload documents through the protected document endpoint")
        return value


class PropertyUpdate(BaseModel):
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def coordinate_pair(self):
        if {"latitude", "longitude"} & self.model_fields_set:
            if not {"latitude", "longitude"} <= self.model_fields_set or (self.latitude is None) != (self.longitude is None):
                raise ValueError("Update latitude and longitude together, or clear both")
        return self

    title: Optional[str] = Field(default=None, min_length=5, max_length=200)
    description: Optional[str] = Field(default=None, min_length=20)
    property_type: Optional[PropertyType] = None
    listing_type: Optional[ListingType] = None
    price: Optional[float] = Field(default=None, gt=0)
    bedrooms: Optional[int] = Field(default=None, ge=0)
    bathrooms: Optional[int] = Field(default=None, ge=0)
    area_sqft: Optional[float] = Field(default=None, gt=0)
    city: Optional[str] = Field(default=None, min_length=2, max_length=100)
    nearby_university: Optional[str] = Field(default=None, max_length=200)
    university_distance_km: Optional[float] = Field(default=None, ge=0)
    owner_phone: Optional[str] = Field(default=None, min_length=11, max_length=20)
    owner_email: Optional[EmailStr] = None
    furnishing: Optional[Furnishing] = None
    rental_type: Optional[RentalType] = None
    is_female_only: Optional[bool] = None
    safety_score: Optional[float] = Field(default=None, ge=0, le=5)
    amenities: Optional[list[str]] = None
    photos: Optional[list[str]] = None
    documents: Optional[list[str]] = None
    has_furniture_for_sale: Optional[bool] = None
    status: Optional[ListingStatus] = None
    owner_name: Optional[str] = Field(default=None, min_length=2)
    address: Optional[str] = Field(default=None, min_length=5)
    area: Optional[str] = Field(default=None, min_length=2)

    @field_validator("documents")
    @classmethod
    def uploaded_documents_only(cls, value):
        raise ValueError("Manage documents through the protected document endpoints")

    @field_validator("title", "description", "property_type", "listing_type", "price", "bedrooms",
                     "bathrooms", "city", "owner_phone", "owner_name", "address", "area", "furnishing",
                     "is_female_only", "amenities", "photos", "has_furniture_for_sale", "status")
    @classmethod
    def required_when_supplied(cls, value):
        if value is None:
            raise ValueError("This field cannot be empty")
        return value


class PropertyOut(PropertyBase):
    id: int
    status: ListingStatus
    created_at: datetime
    updated_at: Optional[datetime] = None
    document_check_status: str = "not_submitted"
    women_safety_status: str = "not_submitted"
    women_safety_reviewed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PropertyPublicOut(PropertyOut):
    documents: list[str] = Field(default_factory=list, exclude=True)
    owner_id: Optional[int] = None


class PropertyListOut(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
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
    women_safety_status: str = "not_submitted"
    women_safety_reviewed_at: Optional[datetime] = None
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
    max_university_distance_km: Optional[float] = Field(default=None, ge=0)
    is_female_only: Optional[bool] = None
    min_safety_score: Optional[float] = Field(default=None, ge=0, le=5)
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
