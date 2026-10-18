from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, Enum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
import enum
from database import Base


class UserRole(str, enum.Enum):
    renter = "renter"
    owner = "owner"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(150), nullable=False, unique=True, index=True)
    password_hash = Column(String(100), nullable=False)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=True)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.renter)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PropertyType(str, enum.Enum):
    apartment = "apartment"
    house = "house"
    office = "office"
    room = "room"


class ListingType(str, enum.Enum):
    rent = "rent"
    sale = "sale"
    sublet = "sublet"


class RentalType(str, enum.Enum):
    monthly = "monthly"
    daily = "daily"
    hourly = "hourly"


class Furnishing(str, enum.Enum):
    furnished = "furnished"
    semi_furnished = "semi_furnished"
    unfurnished = "unfurnished"


class ListingStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    inactive = "inactive"


class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)

    property_type = Column(Enum(PropertyType), nullable=False)
    listing_type = Column(Enum(ListingType), nullable=False)
    rental_type = Column(Enum(RentalType), nullable=True)
    furnishing = Column(Enum(Furnishing), nullable=False)

    price = Column(Float, nullable=False)
    bedrooms = Column(Integer, nullable=False, default=1)
    bathrooms = Column(Integer, nullable=False, default=1)
    area_sqft = Column(Float, nullable=True)

    address = Column(String(300), nullable=False)
    area = Column(String(100), nullable=False, index=True)
    city = Column(String(100), nullable=False, default="Dhaka")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    nearby_university = Column(String(200), nullable=True)
    university_distance_km = Column(Float, nullable=True)

    is_female_only = Column(Boolean, default=False, nullable=False)
    safety_score = Column(Float, nullable=True)

    amenities = Column(JSONB, default=list)
    photos = Column(JSONB, default=list)
    documents = Column(JSONB, default=list)
    has_furniture_for_sale = Column(Boolean, default=False)

    owner_name = Column(String(100), nullable=False)
    owner_phone = Column(String(20), nullable=False)
    owner_email = Column(String(150), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    status = Column(Enum(ListingStatus), default=ListingStatus.active, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ── Booking ──────────────────────────────────────────────────────────────────

class BookingStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    cancelled = "cancelled"


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)

    renter_name = Column(String(100), nullable=False)
    renter_phone = Column(String(20), nullable=False)
    renter_email = Column(String(150), nullable=True)
    renter_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    check_in = Column(DateTime(timezone=True), nullable=False)
    check_out = Column(DateTime(timezone=True), nullable=False)
    rental_type = Column(Enum(RentalType), nullable=False)
    total_price = Column(Float, nullable=False)

    status = Column(Enum(BookingStatus), default=BookingStatus.pending, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── Chat ──────────────────────────────────────────────────────────────────────

class SenderType(str, enum.Enum):
    renter = "renter"
    owner = "owner"


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    session_token = Column(String(64), nullable=False, index=True)
    sender = Column(Enum(SenderType), nullable=False)
    sender_name = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── Safety Votes ──────────────────────────────────────────────────────────────

class SafetyVote(Base):
    __tablename__ = "safety_votes"

    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    rating = Column(Integer, nullable=False)           # 1–5
    comment = Column(String(300), nullable=True)
    voter_name = Column(String(100), nullable=True)
    voter_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── Forum ─────────────────────────────────────────────────────────────────────

class PostType(str, enum.Enum):
    neighborhood = "neighborhood"
    experience = "experience"
    roommate = "roommate"
    report = "report"


class ForumPost(Base):
    __tablename__ = "forum_posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    post_type = Column(Enum(PostType), nullable=False)
    area = Column(String(100), nullable=True)
    nearby_university = Column(String(200), nullable=True)
    author_name = Column(String(100), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    upvotes = Column(Integer, default=0, nullable=False)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ForumComment(Base):
    __tablename__ = "forum_comments"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("forum_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    author_name = Column(String(100), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
