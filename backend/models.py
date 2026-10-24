from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Column, Computed, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
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
    women_safety_status = Column(String(25), nullable=False, default="not_submitted", server_default="not_submitted")
    women_safety_submission = Column(JSONB, nullable=False, default=dict, server_default="{}")
    women_safety_feedback = Column(Text, nullable=True)
    women_safety_version = Column(Integer, nullable=False, default=0, server_default="0")
    women_safety_reviewed_at = Column(DateTime(timezone=True), nullable=True)
    safety_score = Column(Float, nullable=True)

    amenities = Column(JSONB, default=list)
    photos = Column(JSONB, default=list)
    documents = Column(JSONB, default=list)
    has_furniture_for_sale = Column(Boolean, default=False)

    owner_name = Column(String(100), nullable=False)
    owner_phone = Column(String(20), nullable=False)
    owner_email = Column(String(150), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    moderation_reason = Column(Text, nullable=True)   # set when screening moves a listing to `pending`
    document_check_status = Column(String(20), nullable=False, default="not_submitted", server_default="not_submitted")
    document_check_reasons = Column(JSONB, nullable=False, default=list, server_default="[]")
    document_checked_at = Column(DateTime(timezone=True), nullable=True)

    status = Column(Enum(ListingStatus), default=ListingStatus.active, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    archived_at = Column(DateTime(timezone=True), nullable=True, index=True)


class WomenSafetyReview(Base):
    __tablename__ = "women_safety_reviews"

    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewer_name = Column(String(100), nullable=False)
    verdict = Column(String(25), nullable=False)
    version = Column(Integer, nullable=False)
    checklist = Column(JSONB, nullable=False)
    submission = Column(JSONB, nullable=False)
    notes = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PropertyDocument(Base):
    __tablename__ = "property_documents"

    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    stored_name = Column(String(80), nullable=False, unique=True)
    original_name = Column(String(255), nullable=False)
    content_type = Column(String(50), nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)
    text_hash = Column(String(64), nullable=True, index=True)
    extracted_text = Column(Text, nullable=True)
    extraction_error = Column(String(250), nullable=True)
    processed = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── Booking ──────────────────────────────────────────────────────────────────

class BookingStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    cancelled = "cancelled"


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False, index=True)

    renter_name = Column(String(100), nullable=False)
    renter_phone = Column(String(20), nullable=False)
    renter_email = Column(String(150), nullable=True)
    renter_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    check_in = Column(DateTime(timezone=True), nullable=False)
    check_out = Column(DateTime(timezone=True), nullable=False)
    rental_type = Column(Enum(RentalType), nullable=False)
    total_price = Column(Float, nullable=False)

    status = Column(Enum(BookingStatus), default=BookingStatus.pending, nullable=False)
    cancellation_reason = Column(String(30), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    property = relationship("Property", lazy="selectin")


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
    moderation_status = Column(String(10), nullable=False, default="visible", server_default="visible")
    moderation_reason = Column(Text, nullable=True)
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
    moderation_status = Column(String(10), nullable=False, default="visible", server_default="visible")
    moderation_reason = Column(Text, nullable=True)
    upvotes = Column(Integer, default=0, nullable=False)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ForumComment(Base):
    __tablename__ = "forum_comments"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("forum_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    author_name = Column(String(100), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    moderation_status = Column(String(10), nullable=False, default="visible", server_default="visible")
    moderation_reason = Column(Text, nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class InvestigationCase(Base):
    __tablename__ = "investigation_cases"

    id = Column(Integer, primary_key=True)
    reporter_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reporter_name = Column(String(100), nullable=False)
    category = Column(String(30), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(25), nullable=False, default="open", server_default="open", index=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="SET NULL"), nullable=True)
    property_title = Column(String(200), nullable=True)
    booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True)
    booking_reference = Column(Integer, nullable=True)
    forum_post_id = Column(Integer, ForeignKey("forum_posts.id", ondelete="SET NULL"), nullable=True, unique=True)
    assigned_to = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolution = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)


class CaseUpdate(Base):
    __tablename__ = "case_updates"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("investigation_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_name = Column(String(100), nullable=False)
    kind = Column(String(25), nullable=False)
    internal = Column(Boolean, nullable=False, default=False, server_default="false")
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── LLM call log ──────────────────────────────────────────────────────────────

class LLMCall(Base):
    __tablename__ = "llm_calls"

    id = Column(Integer, primary_key=True)
    request_id = Column(String(64), nullable=False, index=True)
    provider = Column(String(20), nullable=False)
    model = Column(String(100), nullable=False)
    purpose = Column(String(50), nullable=False)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    latency_ms = Column(Integer, nullable=False)
    cost_usd = Column(Float, nullable=False, default=0)
    status = Column(String(10), nullable=False)
    error = Column(Text, nullable=True)
    attempts = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


# ── RAG documents (one row per chunk) ─────────────────────────────────────────

EMBEDDING_DIM = 1024  # bge-m3


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", "chunk_index"),
        Index("ix_documents_embedding_hnsw", "embedding", postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64}, postgresql_ops={"embedding": "vector_cosine_ops"}),
        Index("ix_documents_tsv", "tsv", postgresql_using="gin"),
        Index("ix_documents_content_trgm", "content", postgresql_using="gin", postgresql_ops={"content": "gin_trgm_ops"}),
    )

    id = Column(Integer, primary_key=True)
    source_type = Column(String(20), nullable=False)       # listing | post | comment | safety
    source_id = Column(Integer, nullable=False)
    chunk_index = Column(Integer, nullable=False, default=0)
    content = Column(Text, nullable=False)
    tsv = Column(TSVECTOR, Computed("to_tsvector('simple', content)", persisted=True))
    embedding = Column(Vector(EMBEDDING_DIM), nullable=True)
    embedding_model = Column(String(100), nullable=True)
    content_hash = Column(String(64), nullable=False)
    # Metadata for filtering and citations
    property_id = Column(Integer, nullable=True, index=True)
    post_id = Column(Integer, nullable=True, index=True)
    area = Column(String(100), nullable=True, index=True)
    university = Column(String(200), nullable=True)
    lang = Column(String(5), nullable=True)
    source_created_at = Column(DateTime(timezone=True), nullable=True)
    meta = Column(JSONB, default=dict)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ── Background jobs (Postgres queue, FOR UPDATE SKIP LOCKED) ─────────────────

class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_pending", "status", "run_after"),)

    id = Column(Integer, primary_key=True)
    kind = Column(String(50), nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)
    dedupe_key = Column(String(200), nullable=True, index=True)
    status = Column(String(10), nullable=False, default="queued")   # queued | running | done | failed
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)
    last_error = Column(Text, nullable=True)
    result = Column(JSONB, nullable=True)
    run_after = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())



# ── Agent: human-in-the-loop actions and run log ─────────────────────────────

class PendingAction(Base):
    """An action the agent drafted. Nothing happens until the user confirms it in the UI."""
    __tablename__ = "pending_actions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action_type = Column(String(30), nullable=False)            # create_booking | send_message
    scout_run_id = Column(Integer, ForeignKey("scout_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    payload = Column(JSONB, nullable=False)
    summary = Column(JSONB, nullable=False, default=dict)
    status = Column(String(15), nullable=False, default="pending")  # pending | confirmed | cancelled | expired | failed
    result = Column(JSONB, nullable=True)
    request_id = Column(String(64), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    decided_at = Column(DateTime(timezone=True), nullable=True)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True)
    request_id = Column(String(64), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    provider = Column(String(20), nullable=False)
    model = Column(String(100), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    tool_calls = Column(JSONB, nullable=False, default=list)
    citations = Column(JSONB, nullable=False, default=list)
    unsupported_citations = Column(JSONB, nullable=False, default=list)
    llm_steps = Column(Integer, nullable=False, default=0)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0)
    latency_ms = Column(Integer, nullable=False, default=0)
    status = Column(String(15), nullable=False)                  # ok | error | limit
    error = Column(Text, nullable=True)
    client_key = Column(String(80), nullable=True, index=True)   # user:<id> or ip:<hash>, for rate limiting
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


# ── Moderation log ────────────────────────────────────────────────────────────

class ModerationDecision(Base):
    """Every automated screening/moderation decision, with its reasons, plus the admin's review."""
    __tablename__ = "moderation_decisions"

    id = Column(Integer, primary_key=True)
    target_type = Column(String(20), nullable=False)          # listing | post | comment | safety
    target_id = Column(Integer, nullable=False)
    workflow = Column(String(30), nullable=False)             # listing_screen | moderation
    decision = Column(String(10), nullable=False)             # flag | pass
    labels = Column(JSONB, nullable=False, default=list)
    reasons = Column(JSONB, nullable=False, default=list)
    signals = Column(JSONB, nullable=False, default=dict)     # raw scores: similarity, price ratio, llm verdict…
    llm_model = Column(String(100), nullable=True)
    review_status = Column(String(10), nullable=True)         # approved | rejected | removed
    reviewed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (Index("ix_moderation_target", "target_type", "target_id"),)


# ── Scout: background house-hunting agent (LangGraph) ────────────────────────

class Hunt(Base):
    """A student's standing request. Scout checks new listings against it on a schedule."""
    __tablename__ = "hunts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(120), nullable=False)
    brief = Column(Text, nullable=False)                     # the student's own words
    criteria = Column(JSONB, nullable=False, default=dict)   # hard filters (ListingFilters fields)
    preferences = Column(JSONB, nullable=False, default=list)  # soft wishes, ranked by the LLM
    questions = Column(JSONB, nullable=False, default=list)    # things to ask owners if a listing doesn't say
    move_in = Column(DateTime(timezone=True), nullable=True)
    stay_months = Column(Integer, nullable=False, default=6)
    status = Column(String(10), nullable=False, default="active")   # active | paused
    seen_listing_ids = Column(JSONB, nullable=False, default=list)   # already assessed: not re-shortlisted
    rejected_listing_ids = Column(JSONB, nullable=False, default=list)  # the student discarded a draft for these
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ScoutRun(Base):
    __tablename__ = "scout_runs"

    id = Column(Integer, primary_key=True)
    hunt_id = Column(Integer, ForeignKey("hunts.id", ondelete="CASCADE"), nullable=False, index=True)
    thread_id = Column(String(64), nullable=False, unique=True)   # LangGraph checkpoint thread
    trigger = Column(String(10), nullable=False)                 # schedule | manual
    status = Column(String(20), nullable=False, default="running")  # running | awaiting_approval | done | failed
    report = Column(JSONB, nullable=False, default=dict)           # shortlist, skipped, summary, drafted actions
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
