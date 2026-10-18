from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from rag.hybrid import hybrid_search
from rag.indexer import SOURCE_TYPES
from schemas import PropertySearchParams
from services.properties import get_properties, public_summary

router = APIRouter(prefix="/search", tags=["search"])

@router.get("/semantic")
def semantic_search(
    q: Annotated[str, Query(min_length=2, max_length=500)],
    filters: Annotated[PropertySearchParams, Depends()],
    sources: Annotated[str, Query(description="comma-separated: listing,post,comment,safety")] = ",".join(SOURCE_TYPES),
    university: str | None = None,
    k: Annotated[int, Query(ge=1, le=50)] = 10,
    vector: bool = True,
    keyword: bool = True,
    rerank: bool = True,
    db: Session = Depends(get_db),
):
    # `filters.q` would add a substring filter on top of retrieval, which defeats semantic search.
    listing_filters = filters.model_copy(update={"q": None})
    result = hybrid_search(db, q, sources=[s.strip() for s in sources.split(",")], listing_filters=listing_filters,
                           area=None, university=university or listing_filters.nearby_university, k=k,
                           use_vector=vector, use_keyword=keyword, use_rerank=rerank)
    props = {p.id: p for p in get_properties(db, [h.property_id for h in result.hits if h.property_id])}
    return {
        "query": q,
        "stages": result.stages,
        "timings_ms": result.timings_ms,
        "hits": [
            {**{k: v for k, v in h.to_dict().items() if k != "meta"},
             "listing": public_summary(props[h.property_id]) if h.property_id in props else None}
            for h in result.hits
        ],
    }
