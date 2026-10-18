from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from openai import OpenAI

from config import settings
from database import get_db
from models import Property, ListingStatus

router = APIRouter(prefix="/ai", tags=["ai"])

OPENAI_API_KEY = settings.openai_api_key

SYSTEM_PROMPT = """You are the bari.com AI property assistant — a helpful, friendly guide for finding rental properties and sublets in Bangladesh.

When a user describes what they're looking for, analyse the available listings provided and recommend the best matches. Be conversational and concise. Always mention:
- The property title and price
- Why it matches their needs
- Distance to their university if relevant
- Any safety or furnishing highlights

If no listings match, suggest they broaden their filters. Never make up listings that aren't in the data provided.
Reply in plain text (no markdown). Keep responses under 250 words."""


def _format_listings(properties: list) -> str:
    lines = []
    for p in properties[:20]:
        line = (
            f"[ID:{p.id}] {p.title} | {p.listing_type} | "
            f"৳{p.price:,.0f} | {p.area}, {p.city} | "
            f"{p.bedrooms}bed/{p.bathrooms}bath | {p.furnishing} | "
            f"safety:{p.safety_score or 'N/A'}"
        )
        if p.nearby_university:
            line += f" | {p.university_distance_km:.1f}km from {p.nearby_university}"
        if p.is_female_only:
            line += " | women-only"
        lines.append(line)
    return "\n".join(lines)


class ChatMessage(BaseModel):
    role: str
    content: str


class AIRequest(BaseModel):
    messages: list[ChatMessage]
    budget_max: Optional[float] = None
    nearby_university: Optional[str] = None
    listing_type: Optional[str] = None
    is_female_only: Optional[bool] = None


@router.post("/chat")
def ai_chat(payload: AIRequest, db: Session = Depends(get_db)):
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    filters = [Property.status == ListingStatus.active]
    if payload.budget_max:
        filters.append(Property.price <= payload.budget_max)
    if payload.nearby_university:
        filters.append(Property.nearby_university.ilike(f"%{payload.nearby_university}%"))
    if payload.listing_type:
        filters.append(Property.listing_type == payload.listing_type)
    if payload.is_female_only:
        filters.append(Property.is_female_only == True)

    from sqlalchemy import and_
    props = db.query(Property).filter(and_(*filters)).limit(20).all()
    listings_context = _format_listings(props)

    system = SYSTEM_PROMPT
    if listings_context:
        system += f"\n\nAvailable listings:\n{listings_context}"
    else:
        system += "\n\nNo listings currently match the applied filters."

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system}]
               + [{"role": m.role, "content": m.content} for m in payload.messages],
        max_tokens=400,
        temperature=0.7,
    )

    return {"reply": response.choices[0].message.content}
