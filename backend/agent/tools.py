"""Agent tools. Each tool wraps existing service/RAG functions; nothing here re-implements
business logic. Tool outputs carry public fields only, and user-generated text is wrapped as
untrusted data."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy.orm import Session

from agent.guardrails import has_booking_intent, wrap_untrusted
from config import settings
from models import ListingStatus, PendingAction, RentalType, User
from rag.hybrid import hybrid_search
from schemas import PropertySearchParams
from services import bookings as booking_svc
from services import properties as property_svc
from services import safety as safety_svc
from services.errors import ServiceError

DHAKA = timezone(timedelta(hours=6))  # Bangladesh has no DST
University = Literal["BRAC University", "North South University", "Dhaka University", "BUET", "IUB", "AIUB",
                     "East West University", "Jahangirnagar University"]


class ToolError(Exception):
    """An error message that is returned to the model as the tool result."""


@dataclass
class ToolContext:
    user_id: int | None
    request_id: str
    last_user_message: str = ""
    injection_filter: bool = True
    evidence: dict[str, dict] = field(default_factory=dict)  # ref -> {title, snippet, ...}
    pending_actions: list[dict] = field(default_factory=list)

    def cite(self, ref: str, **info) -> str:
        self.evidence.setdefault(ref, {}).update({k: v for k, v in info.items() if v is not None})
        return ref

    def untrusted(self, ref: str, text: str | None) -> str:
        return wrap_untrusted(ref, text, filter_injections=self.injection_filter)


@dataclass
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    fn: Callable[[Session, ToolContext, Any], dict]
    label: Callable[[Any], str]

    def schema(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description, "parameters": clean_schema(self.args.model_json_schema())}}

    def parse(self, raw: dict) -> BaseModel:
        try:
            return self.args.model_validate(raw)
        except ValidationError as e:
            problems = "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors())
            raise ToolError(f"invalid arguments: {problems}") from e


def clean_schema(schema: dict) -> dict:
    """Pydantic JSON schema → the plain subset every tool-calling API accepts (no $defs or titles).

    Optional fields stay nullable (`"type": ["string", "null"]`): providers such as Groq validate tool
    arguments against the schema server-side, and models do send `null` for unused optional arguments."""
    defs = schema.get("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            if "anyOf" in node:
                options = [o for o in node["anyOf"] if o.get("type") != "null"]
                nullable = len(options) < len(node["anyOf"])
                if len(options) == 1:
                    opt = walk(options[0])
                    merged = {**{k: v for k, v in node.items() if k not in ("anyOf", "default")}, **opt}
                    if nullable and isinstance(opt.get("type"), str):
                        merged["type"] = [opt["type"], "null"]
                        if "enum" in merged:
                            merged["enum"] = [*merged["enum"], None]
                    return walk(merged)
            return {k: walk(v) for k, v in node.items() if k not in ("title", "$defs", "default")
                    or (k == "default" and v is not None)}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    out = walk(schema)
    out.pop("title", None)
    return out


# ── Shared argument fragments ────────────────────────────────────────────────

class ListingFilters(BaseModel):
    max_price: float | None = Field(None, gt=0, description="Max rent in BDT. '25k' means 25000.")
    min_price: float | None = Field(None, ge=0)
    bedrooms: int | None = Field(None, ge=0, le=10, description="Minimum number of bedrooms.")
    nearby_university: University | None = None
    area: str | None = Field(None, description="Dhaka neighbourhood, e.g. Badda, Bashundhara, Dhanmondi.")
    max_university_distance_km: float | None = Field(None, gt=0)
    is_female_only: bool | None = Field(None, description="true for women-only listings.")
    min_safety_score: float | None = Field(None, ge=0, le=5, description="Community safety rating 0–5. 'Safe' ≈ 4.")
    furnishing: Literal["furnished", "semi_furnished", "unfurnished"] | None = None
    property_type: Literal["apartment", "house", "room", "office"] | None = None
    listing_type: Literal["rent", "sublet", "sale"] | None = None
    rental_type: Literal["monthly", "daily", "hourly"] | None = None

    def search_params(self, limit: int) -> PropertySearchParams:
        return PropertySearchParams(**self.model_dump(include=set(ListingFilters.model_fields), exclude_none=True),
                                    limit=limit)


def _summary(ctx: ToolContext, p) -> dict:
    # Compact on purpose: every token here is paid for (API) or waited for (local CPU).
    s = {k: v for k, v in property_svc.public_summary(p).items() if v not in (None, [], "") and k != "photos"}
    s["ref"] = ctx.cite(f"listing:{p.id}", title=p.title, area=p.area, kind="listing")
    s["url"] = f"/property/{p.id}"
    return s


def _parse_day(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=DHAKA)


class DateRange(BaseModel):
    check_in: date = Field(description="YYYY-MM-DD")
    check_out: date = Field(description="YYYY-MM-DD, after check_in")

    @model_validator(mode="after")
    def _order(self):
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        return self


def _active_property(db: Session, property_id: int):
    try:
        p = property_svc.get_property(db, property_id)
    except ServiceError as e:
        raise ToolError(f"listing {property_id} does not exist") from e
    if p.status != ListingStatus.active:
        raise ToolError(f"listing {property_id} is not currently available")
    return p


# ── Tools ────────────────────────────────────────────────────────────────────

class SearchPropertiesArgs(ListingFilters):
    limit: int = Field(6, ge=1, le=10)


# Filters a model tends to invent (the user rarely states them). Hard constraints the user gives (budget,
# women-only, bedrooms, university) are never relaxed.
GUESSABLE_FILTERS = ("area", "furnishing", "property_type", "max_university_distance_km", "listing_type")


def _relaxed(a: ListingFilters) -> tuple[ListingFilters, list[str]] | None:
    dropped = [f for f in GUESSABLE_FILTERS if getattr(a, f) is not None]
    return (a.model_copy(update={f: None for f in dropped}), dropped) if dropped else None


def search_properties(db: Session, ctx: ToolContext, a: SearchPropertiesArgs) -> dict:
    params = a.search_params(a.limit)
    props = property_svc.search_properties(db, params)
    out = {"total_matches": property_svc.count_properties(db, params)}
    if not props and (relaxed := _relaxed(a)):
        params = relaxed[0].search_params(a.limit)
        props = property_svc.search_properties(db, params)
        out = {"total_matches": property_svc.count_properties(db, params), "relaxed_filters": relaxed[1],
               "warning": f"No exact matches. These filters were dropped: {', '.join(relaxed[1])}."}
    return {**out, "results": [_summary(ctx, p) for p in props],
            "note": "Structured filter search. Use semantic_search for qualitative needs (quiet, rooftop, near lake…)."}


class SemanticSearchArgs(ListingFilters):
    query: str = Field(min_length=2, description="Natural-language description of what to find (any language).")
    sources: list[Literal["listing", "post", "comment", "safety"]] = Field(
        default_factory=lambda: ["listing"], description="What to search. Default: listings only.")
    k: int = Field(6, ge=1, le=10)


def semantic_search(db: Session, ctx: ToolContext, a: SemanticSearchArgs) -> dict:
    filters = ListingFilters(**a.model_dump(include=set(ListingFilters.model_fields)))
    result = hybrid_search(db, a.query, sources=a.sources, listing_filters=filters.search_params(10),
                           university=a.nearby_university, k=a.k)
    relaxed_note = {}
    if not result.hits and (relaxed := _relaxed(filters)):
        result = hybrid_search(db, a.query, sources=a.sources, listing_filters=relaxed[0].search_params(10),
                               university=a.nearby_university, k=a.k)
        relaxed_note = {"relaxed_filters": relaxed[1],
                        "warning": f"No exact matches. These filters were dropped: {', '.join(relaxed[1])}."}
    props = {p.id: p for p in property_svc.get_properties(db, [h.property_id for h in result.hits if h.property_id])}
    out = []
    for h in result.hits:
        item = {"ref": ctx.cite(h.ref, snippet=h.content[:300], kind=h.source_type, post_id=h.post_id,
                                property_id=h.property_id), "type": h.source_type,
                "text": ctx.untrusted(h.ref, h.content)}
        if h.source_type == "listing" and h.property_id in props:
            item["listing"] = _summary(ctx, props[h.property_id])
            item.pop("text")  # the summary + description below are enough
            item["description"] = ctx.untrusted(h.ref, props[h.property_id].description[:500])
        elif h.property_id:
            item["about_listing"] = f"listing:{h.property_id}"
        out.append(item)
    return {**relaxed_note, "results": out}


class PropertyIdArgs(BaseModel):
    property_id: int = Field(ge=1)


def get_property_details(db: Session, ctx: ToolContext, a: PropertyIdArgs) -> dict:
    p = _active_property(db, a.property_id)
    stats = safety_svc.get_safety_stats(db, p.id, limit=0)
    return {**_summary(ctx, p), "address": p.address, "amenities": p.amenities, "bathrooms": p.bathrooms,
            "area_sqft": p.area_sqft, "has_furniture_for_sale": p.has_furniture_for_sale,
            "description": ctx.untrusted(f"listing:{p.id}", p.description),
            "safety": {"avg_score": stats["avg_score"], "vote_count": stats["vote_count"]},
            "contact": "Owner contact details are shown on the listing page; use the chat there."}


def get_safety_stats(db: Session, ctx: ToolContext, a: PropertyIdArgs) -> dict:
    p = _active_property(db, a.property_id)
    ctx.cite(f"listing:{p.id}", title=p.title, area=p.area, kind="listing")
    stats = safety_svc.get_safety_stats(db, p.id, limit=10)
    comments = []
    for v in stats["votes"]:
        if v["comment"]:
            ref = ctx.cite(f"safety:{v['id']}", snippet=v["comment"][:300], kind="safety",
                           title=f"Safety review of {p.title}", property_id=p.id)
            comments.append({"ref": ref, "rating": v["rating"], "comment": ctx.untrusted(ref, v["comment"])})
    return {"listing": f"listing:{p.id}", "area": p.area, "avg_score": stats["avg_score"],
            "vote_count": stats["vote_count"], "recent_comments": comments}


class SearchForumArgs(BaseModel):
    query: str = Field(min_length=2, description="What to look for in community posts (any language).")
    area: str | None = None
    university: University | None = None
    k: int = Field(5, ge=1, le=8)


def search_forum(db: Session, ctx: ToolContext, a: SearchForumArgs) -> dict:
    result = hybrid_search(db, a.query, sources=["post", "comment"], area=a.area, university=a.university, k=a.k)
    out = []
    for h in result.hits:
        title = h.content.split("\n", 1)[0][:160]
        ref = ctx.cite(h.ref, title=title, snippet=h.content[:300], kind=h.source_type, post_id=h.post_id)
        out.append({"ref": ref, "type": h.source_type, "post": f"post:{h.post_id}", "area": h.area,
                    "text": ctx.untrusted(ref, h.content)})
    return {"results": out, "note": "Forum content is first-hand community opinion, not verified fact."}


class AvailabilityArgs(PropertyIdArgs, DateRange):
    pass


def check_availability(db: Session, ctx: ToolContext, a: AvailabilityArgs) -> dict:
    p = _active_property(db, a.property_id)
    ctx.cite(f"listing:{p.id}", title=p.title, area=p.area, kind="listing")
    clashes = booking_svc.overlapping_bookings(db, p.id, _parse_day(a.check_in), _parse_day(a.check_out))
    return {"listing": f"listing:{p.id}", "available": not clashes,
            "conflicts": [{"check_in": b.check_in.date().isoformat(), "check_out": b.check_out.date().isoformat()}
                          for b in clashes]}


class PriceArgs(AvailabilityArgs):
    rental_type: Literal["monthly", "daily", "hourly"] | None = Field(None, description="Defaults to the listing's.")


def compute_price(db: Session, ctx: ToolContext, a: PriceArgs) -> dict:
    p = _active_property(db, a.property_id)
    ctx.cite(f"listing:{p.id}", title=p.title, area=p.area, kind="listing")
    rt = RentalType(a.rental_type or getattr(p.rental_type, "value", None) or "monthly")
    total = booking_svc.compute_price(p, _parse_day(a.check_in), _parse_day(a.check_out), rt)
    return {"listing": f"listing:{p.id}", "unit_price": p.price, "rental_type": rt.value, "total_bdt": total}


class CompareArgs(BaseModel):
    property_ids: list[int] = Field(min_length=2, max_length=4)


def compare_properties(db: Session, ctx: ToolContext, a: CompareArgs) -> dict:
    rows = []
    for pid in dict.fromkeys(a.property_ids):
        try:
            p = _active_property(db, pid)
        except ToolError as e:
            rows.append({"ref": f"listing:{pid}", "error": str(e)})
            continue
        stats = safety_svc.get_safety_stats(db, p.id, limit=0)
        rows.append({**_summary(ctx, p), "amenities": p.amenities, "safety_votes": stats["vote_count"]})
    return {"comparison": rows}


class DraftBookingArgs(PriceArgs):
    note: str | None = Field(None, max_length=300)


def draft_booking(db: Session, ctx: ToolContext, a: DraftBookingArgs) -> dict:
    """Prepare a booking. It is NOT created: the user must confirm it in the UI."""
    if ctx.user_id is None:
        raise ToolError("the user is not logged in; ask them to log in before booking")
    if not has_booking_intent(ctx.last_user_message):
        raise ToolError("refused: the user has not asked to book. Only draft a booking when the user explicitly asks")
    p = _active_property(db, a.property_id)
    rt = RentalType(a.rental_type or getattr(p.rental_type, "value", None) or "monthly")
    check_in, check_out = _parse_day(a.check_in), _parse_day(a.check_out)
    try:
        _, total = booking_svc.validate_booking(db, p.id, check_in, check_out, rt)
    except ServiceError as e:
        raise ToolError(e.detail) from e
    summary = {"property_id": p.id, "title": p.title, "area": p.area, "check_in": a.check_in.isoformat(),
               "check_out": a.check_out.isoformat(), "rental_type": rt.value, "unit_price": p.price,
               "total_price": total}
    action = PendingAction(
        user_id=ctx.user_id, action_type="create_booking", request_id=ctx.request_id,
        payload={"property_id": p.id, "check_in": check_in.isoformat(), "check_out": check_out.isoformat(),
                 "rental_type": rt.value, "note": a.note},
        summary=summary, expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.pending_action_ttl_min),
    )
    db.add(action)
    db.commit()
    ctx.cite(f"listing:{p.id}", title=p.title, area=p.area, kind="listing")
    ctx.pending_actions.append({"id": action.id, "type": "create_booking", "summary": summary,
                                "expires_at": action.expires_at.isoformat()})
    return {"status": "awaiting_user_confirmation", "pending_action_id": action.id, "summary": summary,
            "important": "The booking has NOT been created. Tell the user to review and click Confirm."}


TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("search_properties", "Find active listings with structured filters (price, bedrooms, university, "
         "women-only, safety score…). Use this when the user states concrete constraints.",
         SearchPropertiesArgs, search_properties, lambda a: "Searching listings…"),
    Tool("semantic_search", "Meaning-based search (English or Bangla) over listings and, optionally, forum posts, "
         "comments and safety reviews. Combine with filters for hard constraints.",
         SemanticSearchArgs, semantic_search, lambda a: f"Searching for “{a.query[:40]}”…"),
    Tool("get_property_details", "Full public details of one listing.", PropertyIdArgs, get_property_details,
         lambda a: f"Reading listing #{a.property_id}…"),
    Tool("get_safety_stats", "Community safety rating and recent safety reviews for a listing.",
         PropertyIdArgs, get_safety_stats, lambda a: f"Checking safety of #{a.property_id}…"),
    Tool("search_forum", "Search community forum posts and comments about areas, safety, flooding, landlords, "
         "scams or roommates.", SearchForumArgs, search_forum, lambda a: "Searching the community forum…"),
    Tool("check_availability", "Check whether a listing is free between two dates.", AvailabilityArgs,
         check_availability, lambda a: f"Checking availability of #{a.property_id}…"),
    Tool("compute_price", "Compute the total price for a stay.", PriceArgs, compute_price,
         lambda a: f"Computing price for #{a.property_id}…"),
    Tool("compare_properties", "Side-by-side comparison of 2–4 listings.", CompareArgs, compare_properties,
         lambda a: "Comparing listings…"),
    Tool("draft_booking", "Prepare a booking for the logged-in user. This does NOT book: the user must "
         "click Confirm in the app. Only call it when the user explicitly asks to book.",
         DraftBookingArgs, draft_booking, lambda a: f"Preparing a booking for #{a.property_id}…"),
]}


def tool_schemas() -> list[dict]:
    return [t.schema() for t in TOOLS.values()]


def current_user(db: Session, user_id: int | None) -> User | None:
    return db.get(User, user_id) if user_id else None
