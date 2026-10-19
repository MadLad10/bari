"""Keep `documents` in sync with the source tables. Idempotent: unchanged chunks are never re-embedded."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from models import Document, ForumComment, ForumPost, ListingStatus, Property, SafetyVote
from rag.chunking import Chunk, comment_chunks, listing_chunks, post_chunks, safety_chunks
from rag.embeddings import get_embedder

SOURCE_TYPES = ("listing", "post", "comment", "safety")


def build_chunks(db: Session, source_type: str, source_id: int) -> list[Chunk]:
    """Chunks a source should currently have. An empty list means it should not be searchable."""
    if source_type == "listing":
        p = db.get(Property, source_id)
        return listing_chunks(p) if p and p.status == ListingStatus.active else []
    if source_type == "safety":
        v = db.get(SafetyVote, source_id)
        prop = db.get(Property, v.property_id) if v else None
        return safety_chunks(v, prop) if v and prop and prop.status == ListingStatus.active and _visible(v) else []
    if source_type == "post":
        post = db.get(ForumPost, source_id)
        return post_chunks(post) if post and _visible(post) else []
    if source_type == "comment":
        c = db.get(ForumComment, source_id)
        post = db.get(ForumPost, c.post_id) if c else None
        return comment_chunks(c, post) if c and post and _visible(c) and _visible(post) else []
    raise ValueError(f"unknown source_type {source_type!r}")


def _visible(obj) -> bool:
    return getattr(obj, "moderation_status", "visible") in (None, "visible")


def _plan(db: Session, source_type: str, source_id: int, embedder) -> tuple[list[Chunk], dict, list[Chunk]]:
    """Chunks the source should have, its current documents, and which chunks need (re-)embedding."""
    # Serialise indexing of the same source (worker vs. reindex script), held until commit.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"index:{source_type}:{source_id}"})
    chunks = build_chunks(db, source_type, source_id)
    existing = {d.chunk_index: d for d in
                db.query(Document).filter_by(source_type=source_type, source_id=source_id).all()}
    stale = [c for c in chunks if c.chunk_index not in existing
             or existing[c.chunk_index].content_hash != c.content_hash
             or existing[c.chunk_index].embedding_model != embedder.model]
    return chunks, existing, stale


def _apply(db: Session, source_type: str, source_id: int, chunks, existing, stale, vectors, model: str) -> dict:
    for chunk, vec in zip(stale, vectors):
        doc = existing.get(chunk.chunk_index) or Document(source_type=source_type, source_id=source_id,
                                                          chunk_index=chunk.chunk_index)
        doc.content, doc.content_hash, doc.embedding, doc.embedding_model = chunk.content, chunk.content_hash, vec, model
        doc.property_id, doc.post_id, doc.area, doc.university = chunk.property_id, chunk.post_id, chunk.area, chunk.university
        doc.lang, doc.source_created_at, doc.meta = chunk.lang, chunk.source_created_at, chunk.meta
        db.add(doc)
    # Metadata can change without the text changing (e.g. a post gets linked to a listing).
    for chunk in chunks:
        doc = existing.get(chunk.chunk_index)
        if doc is not None and chunk not in stale:
            doc.property_id, doc.area, doc.meta = chunk.property_id, chunk.area, chunk.meta
    keep = {c.chunk_index for c in chunks}
    removed = [d for idx, d in existing.items() if idx not in keep]
    for d in removed:
        db.delete(d)
    return {"chunks": len(chunks), "embedded": len(stale), "removed": len(removed)}


def index_source(db: Session, source_type: str, source_id: int) -> dict:
    embedder = get_embedder()
    chunks, existing, stale = _plan(db, source_type, source_id, embedder)
    vectors = embedder.embed([c.content for c in stale]) if stale else []
    result = _apply(db, source_type, source_id, chunks, existing, stale, vectors, embedder.model)
    db.commit()
    return result


def index_many(db: Session, sources: list[tuple[str, int]]) -> dict:
    """Index several sources with one batched embedding call (hosted APIs count requests per day)."""
    embedder = get_embedder()
    plans = [(st, sid, *_plan(db, st, sid, embedder)) for st, sid in sources]
    texts = [c.content for *_, stale in plans for c in stale]
    try:
        vectors = iter(embedder.embed(texts) if texts else [])
    except Exception:
        db.rollback()  # release the advisory locks; nothing was written
        raise
    totals = {"sources": len(sources), "chunks": 0, "embedded": 0, "removed": 0}
    for st, sid, chunks, existing, stale in plans:
        r = _apply(db, st, sid, chunks, existing, stale, [next(vectors) for _ in stale], embedder.model)
        for k in ("chunks", "embedded", "removed"):
            totals[k] += r[k]
    db.commit()
    return totals


def all_sources(db: Session) -> list[tuple[str, int]]:
    out = [("listing", i) for (i,) in db.query(Property.id).filter(Property.status == ListingStatus.active)]
    out += [("post", i) for (i,) in db.query(ForumPost.id)]
    out += [("comment", i) for (i,) in db.query(ForumComment.id)]
    out += [("safety", i) for (i,) in db.query(SafetyVote.id).filter(SafetyVote.comment.isnot(None))]
    return out


def enqueue_index(db: Session, source_type: str, source_id: int) -> None:
    from jobs.queue import enqueue
    enqueue(db, "index", {"source_type": source_type, "source_id": source_id},
            dedupe_key=f"index:{source_type}:{source_id}")
