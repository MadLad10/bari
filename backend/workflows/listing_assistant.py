"""Helps an owner write a better listing: a description draft, a missing-info checklist and a price check."""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from agent.guardrails import scrub_pii
from llm.base import LLMError
from llm.client import get_llm
from services.properties import public_summary
from workflows.comparables import price_stats, price_verdict, similar_listings

DESCRIBE_PROMPT = """You write rental listing descriptions for bari, a student housing platform in Dhaka.
Write {language} prose of 70–130 words using ONLY the facts in the JSON. Never invent amenities, rules,
distances, prices or availability. Never include phone numbers or emails. Mention who it suits (e.g. female
students if women-only), the distance to the university, and the most useful amenities. No headings, no emojis."""


def _facts(f: dict) -> dict:
    keep = ("title", "property_type", "listing_type", "rental_type", "furnishing", "price", "bedrooms", "bathrooms",
            "area_sqft", "area", "nearby_university", "university_distance_km", "is_female_only", "amenities",
            "has_furniture_for_sale", "description")
    return {k: f[k] for k in keep if f.get(k) not in (None, "", [])}


def template_description(f: dict) -> str:
    """Deterministic fallback when no LLM is available."""
    kind = "room" if f.get("property_type") == "room" else f"{f.get('bedrooms', 1)}-bedroom {f.get('property_type', 'flat')}"
    s = [f"{str(f.get('furnishing', '')).replace('_', '-').capitalize()} {kind} in {f.get('area', 'Dhaka')}".strip()]
    if f.get("nearby_university"):
        s[0] += f", {f.get('university_distance_km', '?')} km from {f['nearby_university']}"
    s[0] += "."
    if f.get("is_female_only"):
        s.append("Reserved for female tenants.")
    if f.get("amenities"):
        s.append("Amenities: " + ", ".join(f["amenities"]) + ".")
    if f.get("price"):
        s.append(f"Rent ৳{float(f['price']):,.0f}{'/month' if f.get('rental_type', 'monthly') == 'monthly' else ''}.")
    return " ".join(s)


def missing_info(f: dict) -> list[dict]:
    items = []

    def need(cond, field, severity, message):
        if cond:
            items.append({"field": field, "severity": severity, "message": message})

    desc = f.get("description") or ""
    need(not f.get("title") or len(f["title"]) < 5, "title", "required", "Add a clear title (at least 5 characters).")
    need(len(desc) < 20, "description", "required", "Add a description (at least 20 characters).")
    need(not f.get("price"), "price", "required", "Set the rent.")
    need(not f.get("area"), "area", "required", "Choose the neighbourhood.")
    need(not f.get("address"), "address", "required", "Add the address (only the area is shown publicly in search).")
    need(not f.get("nearby_university"), "nearby_university", "recommended",
         "Students search by university: add the nearest one.")
    need(f.get("nearby_university") and not f.get("university_distance_km"), "university_distance_km",
         "recommended", "Add the distance to campus in km.")
    need(len(f.get("amenities") or []) < 3, "amenities", "recommended",
         "List at least 3 amenities (gas line/cylinder, WiFi, generator/IPS, security…).")
    need(len(f.get("photos") or []) < 3, "photos", "recommended", "Listings with 3+ photos get far more enquiries.")
    need(not f.get("area_sqft") and f.get("property_type") != "room", "area_sqft", "recommended", "Add the size in sqft.")
    need(not re.search(r"advance|deposit|অগ্রিম", desc, re.I), "description", "recommended",
         "Say how much advance/deposit you need.")
    need(not re.search(r"available|from (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|পাওয়া যাবে|থেকে", desc, re.I),
         "description", "recommended", "Say when it's available from.")
    need(f.get("property_type") == "room" and f.get("is_female_only") is None, "is_female_only", "recommended",
         "State whether the room is women-only.")
    _, pii = scrub_pii(desc)
    need(pii > 0, "description", "required",
         "Remove phone numbers/emails from the description: renters contact you through bari chat.")
    return items


def assist(db: Session, fields: dict, *, language: str = "en", request_id: str | None = None) -> dict:
    facts = _facts(fields)
    description, source = None, "template"
    try:
        llm = get_llm()
        resp = llm.chat([
            {"role": "system", "content": DESCRIBE_PROMPT.format(language="Bangla" if language == "bn" else "English")},
            {"role": "user", "content": str(facts)}], purpose="listing_assistant", request_id=request_id,
            temperature=0.4, max_tokens=350)
        description, _ = scrub_pii(resp.content.strip())
        source = llm.model
    except LLMError:
        pass
    if not description:
        description = template_description(fields)

    comps = similar_listings(db, fields, k=8, exclude_id=fields.get("id")) if fields.get("area") or fields.get("nearby_university") else []
    stats = price_stats([p.price for p in comps])
    verdict, ratio = price_verdict(float(fields.get("price") or 0), stats)
    return {
        "description": description,
        "description_source": source,
        "missing_info": missing_info(fields),
        "price_check": {"verdict": verdict, "ratio_to_median": round(ratio, 2) if ratio else None, "stats": stats,
                        "comparables": [{**public_summary(p), "ref": f"listing:{p.id}"} for p in comps]},
    }
