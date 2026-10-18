"""Turn database rows into retrievable chunks.

Strategy per source:
- listing: one chunk. Title, place, structured facts and description. Safety score is left out on
  purpose: it changes with every vote, and it's a filter, not something to match text against.
- safety vote: one chunk per vote that has a comment, prefixed with the listing it's about.
- forum post: a header (id, type, title, area) plus the body. Bodies over CHUNK_CHARS are split on
  sentence boundaries (English . ? ! and Bangla ।) with a one-sentence overlap. Every chunk repeats
  the header, so it stands on its own.
- comment: one chunk, prefixed with the parent post's title for context.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

CHUNK_CHARS = 700
_SENTENCE = re.compile(r"(?<=[.!?।])\s+|\n{2,}")


@dataclass
class Chunk:
    source_type: str
    source_id: int
    chunk_index: int
    content: str
    property_id: int | None = None
    post_id: int | None = None
    area: str | None = None
    university: str | None = None
    lang: str | None = None
    source_created_at: object = None
    meta: dict = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()


def detect_lang(text: str) -> str:
    bangla = sum("ঀ" <= ch <= "৿" for ch in text)
    letters = sum(ch.isalpha() for ch in text) or 1
    return "bn" if bangla / letters > 0.3 else "en"


def split_text(text: str, limit: int = CHUNK_CHARS) -> list[str]:
    text = text.strip()
    if len(text) <= limit:
        return [text]
    sentences = [s.strip() for s in _SENTENCE.split(text) if s and s.strip()]
    chunks, current = [], []
    for sent in sentences:
        while len(sent) > limit:  # a single giant "sentence": hard wrap
            chunks.append(sent[:limit])
            sent = sent[limit:]
        if current and len(" ".join(current + [sent])) > limit:
            chunks.append(" ".join(current))
            current = [current[-1]] if len(current[-1]) < limit // 3 else []  # one-sentence overlap
        current.append(sent)
    if current:
        chunks.append(" ".join(current))
    return chunks


def _enum(v) -> str:
    return getattr(v, "value", v) or ""


def listing_chunks(p) -> list[Chunk]:
    kind = "room" if _enum(p.property_type) == "room" else f"{p.bedrooms}-bed {_enum(p.property_type)}"
    unit = {"monthly": "/month", "daily": "/day", "hourly": "/hour"}.get(_enum(p.rental_type), "")
    lines = [
        f"Listing #{p.id}: {p.title}",
        f"Area: {p.area}, {p.city}" + (f" · near {p.nearby_university} ({p.university_distance_km} km)"
                                       if p.nearby_university else ""),
        f"{kind}, {_enum(p.listing_type)}, {_enum(p.furnishing).replace('_', '-')} · ৳{p.price:,.0f}{unit}"
        + (" · women-only" if p.is_female_only else ""),
    ]
    if p.amenities:
        lines.append("Amenities: " + ", ".join(p.amenities))
    content = "\n".join(lines) + "\n\n" + p.description
    return [Chunk("listing", p.id, 0, content, property_id=p.id, area=p.area, university=p.nearby_university,
                  lang=detect_lang(p.title + p.description), source_created_at=p.created_at,
                  meta={"price": p.price, "women_only": p.is_female_only})]


def safety_chunks(v, prop) -> list[Chunk]:
    if not v.comment or not v.comment.strip():
        return []
    content = (f"Safety rating {v.rating}/5 for listing #{prop.id} ({prop.title}, {prop.area}): {v.comment}")
    return [Chunk("safety", v.id, 0, content, property_id=prop.id, area=prop.area, university=prop.nearby_university,
                  lang=detect_lang(v.comment), source_created_at=v.created_at, meta={"rating": v.rating})]


def post_chunks(post) -> list[Chunk]:
    header = f"Forum post #{post.id} [{_enum(post.post_type)}] {post.title}" + (f" ({post.area})" if post.area else "")
    parts = split_text(post.body)
    return [Chunk("post", post.id, i, f"{header}\n{part}", property_id=post.property_id, post_id=post.id,
                  area=post.area, university=post.nearby_university, lang=detect_lang(post.title + post.body),
                  source_created_at=post.created_at, meta={"post_type": _enum(post.post_type), "parts": len(parts)})
            for i, part in enumerate(parts)]


def comment_chunks(c, post) -> list[Chunk]:
    content = f"Comment on forum post #{post.id} \"{post.title}\": {c.content}"
    return [Chunk("comment", c.id, 0, content, property_id=post.property_id, post_id=post.id, area=post.area,
                  university=post.nearby_university, lang=detect_lang(c.content), source_created_at=c.created_at)]
