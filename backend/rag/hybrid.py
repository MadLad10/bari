"""Hybrid retrieval: structured filters → (vector ∥ keyword) → Reciprocal Rank Fusion → cross-encoder rerank.

Each stage can be switched off, which the eval uses for its ablation table.
"""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

import logging

from config import settings
from llm.base import LLMError
from models import Document, Property
from rag.chunking import detect_lang
from rag.embeddings import get_embedder
from rag.indexer import SOURCE_TYPES
from rag.rerank import get_reranker
from schemas import PropertySearchParams
from services.properties import build_filters

log = logging.getLogger("bari.rag")
RRF_K = 60
# Keyword search can't match across languages (a Bangla query vs an English listing), and equal-weight RRF then
# buries a document that is #1 for vector search but absent from the keyword list. The eval showed Bangla hit@5
# fall from 1.00 (vector only) to 0.50 (equal-weight hybrid), so Bangla-script queries get a smaller keyword weight.
KEYWORD_WEIGHT_LATIN = 1.0
KEYWORD_WEIGHT_BANGLA = 0.1  # swept 0.25 / 0.1 / 0 on the 7 Bangla eval queries (small: see README caveat)


def keyword_weight_for(query: str) -> float:
    return KEYWORD_WEIGHT_BANGLA if detect_lang(query) == "bn" else KEYWORD_WEIGHT_LATIN
_TOKEN = re.compile(r"[\wঀ-৿]+", re.UNICODE)
STOPWORDS = {
    # English
    "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for", "near", "is", "are", "it", "i", "me", "my",
    "with", "from", "under", "below", "any", "some", "what", "how", "which", "who", "can", "do", "does", "there",
    "find", "show", "want", "need", "looking", "please", "place", "about", "that", "this", "be", "by", "than",
    # Bangla
    "এর", "ও", "কি", "কী", "আছে", "জন্য", "থেকে", "কাছে", "একটা", "একটি", "আমি", "আমার", "কোন", "কোথায়", "মধ্যে",
    "এবং", "বা", "না", "হবে", "চাই", "দরকার", "কেমন",
}


@dataclass
class Hit:
    doc_id: int
    source_type: str
    source_id: int
    chunk_index: int
    content: str
    property_id: int | None
    post_id: int | None
    area: str | None
    lang: str | None
    meta: dict
    score: float = 0.0
    vector_rank: int | None = None
    keyword_rank: int | None = None
    rerank_score: float | None = None

    @property
    def ref(self) -> str:
        """Citation handle used by the agent: listing:12, post:40, comment:7, safety:606."""
        return f"{self.source_type}:{self.source_id}"

    def to_dict(self) -> dict:
        return {**asdict(self), "ref": self.ref}


@dataclass
class SearchResult:
    hits: list[Hit]
    timings_ms: dict = field(default_factory=dict)
    stages: dict = field(default_factory=dict)


def keyword_tsquery(query: str) -> str | None:
    """OR of prefix terms: 'women:* | brac:* | ছাত্রী:*'. Prefixes cover Bangla inflections (no stemmer)."""
    terms = []
    for tok in _TOKEN.findall(query.lower()):
        if tok in STOPWORDS or (len(tok) < 3 and not tok.isdigit()):
            continue
        terms.append(f"{tok}:*")
    return " | ".join(dict.fromkeys(terms)) or None


def _where(sources, listing_filters: PropertySearchParams | None, area, university):
    allowed = select(Property.id).where(and_(*build_filters(listing_filters or PropertySearchParams())))
    clauses = [Document.source_type.in_(sources)]
    listing_like = Document.source_type.in_(("listing", "safety"))
    # Listing and safety chunks must belong to an active listing that passes the structured filters.
    clauses.append(or_(~listing_like, Document.property_id.in_(allowed)))
    if area:
        clauses.append(Document.area.ilike(f"%{area}%"))
    if university:
        clauses.append(Document.university.ilike(f"%{university}%"))
    return and_(*clauses)


def _vector(db: Session, qvec, where, limit: int) -> list[Document]:
    # pgvector ≥0.8: keep scanning the HNSW index until enough rows pass the filters.
    db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    db.execute(text("SET LOCAL hnsw.ef_search = 100"))
    dist = Document.embedding.cosine_distance(qvec)
    return list(db.scalars(select(Document).where(where, Document.embedding.isnot(None)).order_by(dist).limit(limit)))


def _keyword(db: Session, query: str, where, limit: int) -> list[Document]:
    tsq = keyword_tsquery(query)
    if not tsq:
        return []
    q = func.to_tsquery("simple", tsq)
    rank = func.ts_rank_cd(Document.tsv, q, 32)
    return list(db.scalars(select(Document).where(where, Document.tsv.op("@@")(q)).order_by(rank.desc()).limit(limit)))


def _to_hit(d: Document) -> Hit:
    return Hit(doc_id=d.id, source_type=d.source_type, source_id=d.source_id, chunk_index=d.chunk_index,
               content=d.content, property_id=d.property_id, post_id=d.post_id, area=d.area, lang=d.lang,
               meta=d.meta or {})


def hybrid_search(db: Session, query: str, *, sources: tuple[str, ...] | list[str] = SOURCE_TYPES,
                  listing_filters: PropertySearchParams | None = None, area: str | None = None,
                  university: str | None = None, k: int = 8, candidates: int = 40, rerank_top: int | None = None,
                  use_vector: bool = True, use_keyword: bool = True, use_rerank: bool = True,
                  one_per_source: bool = True, keyword_weight: float | None = None) -> SearchResult:
    sources = tuple(s for s in sources if s in SOURCE_TYPES) or SOURCE_TYPES
    where = _where(sources, listing_filters, area, university)
    timings: dict[str, int] = {}
    hits: dict[int, Hit] = {}
    fused: dict[int, float] = {}

    vector_ok = use_vector
    if use_vector:
        t = time.perf_counter()
        try:
            qvec = get_embedder().embed_query(query)
        except LLMError as e:
            # Embedding API rate-limited or down: degrade to keyword search instead of failing the request.
            log.warning("query embedding failed, falling back to keyword search: %s", e)
            vector_ok, use_keyword = False, True
        timings["embed"] = int((time.perf_counter() - t) * 1000)
    if vector_ok:
        t = time.perf_counter()
        for rank, d in enumerate(_vector(db, qvec, where, candidates), start=1):
            h = hits.setdefault(d.id, _to_hit(d))
            h.vector_rank = rank
            fused[d.id] = fused.get(d.id, 0) + 1 / (RRF_K + rank)
        timings["vector"] = int((time.perf_counter() - t) * 1000)
    if use_keyword:
        t = time.perf_counter()
        w = keyword_weight_for(query) if keyword_weight is None else keyword_weight
        for rank, d in enumerate(_keyword(db, query, where, candidates), start=1):
            h = hits.setdefault(d.id, _to_hit(d))
            h.keyword_rank = rank
            fused[d.id] = fused.get(d.id, 0) + w / (RRF_K + rank)
        timings["keyword"] = int((time.perf_counter() - t) * 1000)

    ranked = sorted(hits.values(), key=lambda h: fused[h.doc_id], reverse=True)
    for h in ranked:
        h.score = round(fused[h.doc_id], 6)

    reranker = get_reranker() if use_rerank else None
    rerank_top = rerank_top or settings.rerank_top
    if reranker and ranked:
        t = time.perf_counter()
        top = ranked[:rerank_top]
        for h, s in zip(top, reranker.score(query, [h.content for h in top])):
            h.rerank_score = round(s, 4)
            h.score = h.rerank_score
        ranked = sorted(top, key=lambda h: h.score, reverse=True) + ranked[rerank_top:]
        timings["rerank"] = int((time.perf_counter() - t) * 1000)

    if one_per_source:  # long posts have several chunks: keep each source's best one
        seen, unique = set(), []
        for h in ranked:
            if h.ref not in seen:
                seen.add(h.ref)
                unique.append(h)
        ranked = unique

    return SearchResult(hits=ranked[:k], timings_ms=timings,
                        stages={"vector": vector_ok if use_vector else False, "keyword": use_keyword,
                                "rerank": bool(reranker),
                                **({"vector_unavailable": True} if use_vector and not vector_ok else {})})
