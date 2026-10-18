"""Moderator tools: review queue for flagged listings and held content, decision log, LLM usage."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from deps import require_role
from models import (AgentRun, ForumComment, ForumPost, LLMCall, ListingStatus, ModerationDecision, Property,
                    SafetyVote, User, UserRole)
from rag.indexer import enqueue_index
from services.errors import NotFound
from services.properties import public_summary

router = APIRouter(prefix="/admin", tags=["admin"])
admin_only = require_role(UserRole.admin)
CONTENT = {"post": ForumPost, "comment": ForumComment, "safety": SafetyVote}


def _latest_decision(db: Session, kind: str, item_id: int) -> dict | None:
    d = (db.query(ModerationDecision).filter_by(target_type=kind, target_id=item_id)
         .order_by(ModerationDecision.id.desc()).first())
    return d and {"id": d.id, "labels": d.labels, "reasons": d.reasons, "signals": d.signals, "llm_model": d.llm_model,
                  "created_at": d.created_at.isoformat() if d.created_at else None}


def _text(kind, obj) -> dict:
    if kind == "post":
        return {"title": obj.title, "text": obj.body, "author": obj.author_name}
    if kind == "comment":
        return {"title": f"Comment on post #{obj.post_id}", "text": obj.content, "author": obj.author_name}
    return {"title": f"Safety review of listing #{obj.property_id} ({obj.rating}/5)", "text": obj.comment,
            "author": obj.voter_name or "Anonymous"}


@router.get("/queue")
def review_queue(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    listings = (db.query(Property).filter(Property.status == ListingStatus.pending, Property.moderation_reason.isnot(None))
                .order_by(Property.created_at.desc()).all())
    content = []
    for kind, model in CONTENT.items():
        for obj in db.query(model).filter(model.moderation_status == "held").all():
            content.append({"kind": kind, "id": obj.id, **_text(kind, obj), "reason": obj.moderation_reason,
                            "decision": _latest_decision(db, kind, obj.id),
                            "created_at": obj.created_at.isoformat() if obj.created_at else None})
    return {
        "listings": [{**public_summary(p), "description": p.description, "owner_name": p.owner_name,
                      "reason": p.moderation_reason, "decision": _latest_decision(db, "listing", p.id)}
                     for p in listings],
        "content": sorted(content, key=lambda c: c["created_at"] or "", reverse=True),
    }


def _review(db: Session, kind: str, item_id: int, status: str, admin: User) -> None:
    d = (db.query(ModerationDecision).filter_by(target_type=kind, target_id=item_id)
         .order_by(ModerationDecision.id.desc()).first())
    if d:
        d.review_status, d.reviewed_by, d.reviewed_at = status, admin.id, datetime.now(timezone.utc)


@router.post("/listings/{property_id}/{verdict}")
def review_listing(property_id: int, verdict: Literal["approve", "reject"], db: Session = Depends(get_db),
                   admin: User = Depends(admin_only)):
    prop = db.get(Property, property_id)
    if not prop:
        raise NotFound("Property not found")
    prop.status = ListingStatus.active if verdict == "approve" else ListingStatus.inactive
    prop.moderation_reason = None if verdict == "approve" else prop.moderation_reason
    _review(db, "listing", property_id, "approved" if verdict == "approve" else "rejected", admin)
    enqueue_index(db, "listing", property_id)
    db.commit()
    return {"id": property_id, "status": prop.status.value}


@router.post("/content/{kind}/{item_id}/{verdict}")
def review_content(kind: Literal["post", "comment", "safety"], item_id: int, verdict: Literal["approve", "remove"],
                   db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    obj = db.get(CONTENT[kind], item_id)
    if not obj:
        raise NotFound("Not found")
    obj.moderation_status = "visible" if verdict == "approve" else "removed"
    _review(db, kind, item_id, "approved" if verdict == "approve" else "removed", admin)
    enqueue_index(db, kind, item_id)
    db.commit()
    return {"kind": kind, "id": item_id, "moderation_status": obj.moderation_status}


@router.get("/decisions")
def decisions(limit: int = Query(50, le=500), db: Session = Depends(get_db), _: User = Depends(admin_only)):
    rows = db.query(ModerationDecision).order_by(ModerationDecision.id.desc()).limit(limit).all()
    return [{"id": d.id, "target": f"{d.target_type}:{d.target_id}", "workflow": d.workflow, "decision": d.decision,
             "labels": d.labels, "reasons": d.reasons, "review_status": d.review_status,
             "created_at": d.created_at.isoformat() if d.created_at else None} for d in rows]


@router.get("/llm-usage")
def llm_usage(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    rows = (db.query(LLMCall.provider, LLMCall.model, LLMCall.purpose, func.count(LLMCall.id),
                     func.sum(LLMCall.prompt_tokens), func.sum(LLMCall.completion_tokens), func.sum(LLMCall.cost_usd),
                     func.avg(LLMCall.latency_ms), func.count(LLMCall.id).filter(LLMCall.status == "error"))
            .group_by(LLMCall.provider, LLMCall.model, LLMCall.purpose).all())
    runs = db.query(AgentRun).order_by(AgentRun.id.desc()).limit(20).all()
    return {
        "by_model": [{"provider": r[0], "model": r[1], "purpose": r[2], "calls": r[3], "prompt_tokens": r[4] or 0,
                      "completion_tokens": r[5] or 0, "cost_usd": round(r[6] or 0, 6),
                      "avg_latency_ms": int(r[7] or 0), "errors": int(r[8] or 0)} for r in rows],
        "recent_agent_runs": [{"id": a.id, "question": a.question[:200], "status": a.status, "model": a.model,
                               "tools": [t["tool"] for t in a.tool_calls], "citations": a.citations,
                               "unsupported": a.unsupported_citations, "latency_ms": a.latency_ms,
                               "cost_usd": a.cost_usd, "created_at": a.created_at.isoformat() if a.created_at else None}
                              for a in runs],
    }
