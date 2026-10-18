"""Find similar listings by retrieval and summarise their prices."""
from __future__ import annotations

import statistics

from sqlalchemy.orm import Session

from rag.hybrid import hybrid_search
from schemas import PropertySearchParams
from services.properties import get_properties


def listing_text(f: dict) -> str:
    kind = "room" if f.get("property_type") == "room" else f"{f.get('bedrooms') or ''}-bed {f.get('property_type') or ''}"
    parts = [f.get("title") or "", f"{kind} in {f.get('area') or ''}",
             f"near {f['nearby_university']}" if f.get("nearby_university") else "",
             ", ".join(f.get("amenities") or []), (f.get("description") or "")[:400]]
    return " · ".join(p for p in parts if p.strip())


def similar_listings(db: Session, fields: dict, *, k: int = 8, exclude_id: int | None = None) -> list:
    params = PropertySearchParams(
        property_type=fields.get("property_type"), rental_type=fields.get("rental_type") or "monthly",
        nearby_university=fields.get("nearby_university"), limit=50)
    hits = hybrid_search(db, listing_text(fields), sources=["listing"], listing_filters=params, k=30,
                         use_rerank=False).hits
    props = {p.id: p for p in get_properties(db, [h.property_id for h in hits])}
    beds = fields.get("bedrooms")
    out = []
    for h in hits:
        p = props.get(h.property_id)
        if not p or p.id == exclude_id:
            continue
        if fields.get("property_type") != "room" and beds and abs((p.bedrooms or 0) - beds) > 1:
            continue
        out.append(p)
        if len(out) == k:
            break
    return out


def price_stats(prices: list[float]) -> dict | None:
    if len(prices) < 3:
        return None
    q = statistics.quantiles(sorted(prices), n=4)
    return {"n": len(prices), "median": statistics.median(prices), "p25": q[0], "p75": q[2],
            "min": min(prices), "max": max(prices)}


def price_verdict(price: float, stats: dict | None) -> tuple[str, float | None]:
    if not stats or not price:
        return "unknown", None
    ratio = price / stats["median"]
    if ratio < 0.4:
        return "suspiciously_low", ratio
    if price < stats["p25"]:
        return "below_typical", ratio
    if price > stats["p75"] * 1.1:
        return "above_typical", ratio
    return "typical", ratio
