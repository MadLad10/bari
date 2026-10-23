"""Local, deterministic document checks. Passing checks does not establish legal ownership."""
from __future__ import annotations

import csv
import hashlib
import io
import subprocess
import tempfile
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import or_

from config import settings
from jobs.queue import enqueue
from models import ListingStatus, Property, PropertyDocument, User
from rag.indexer import enqueue_index
from services.errors import BadRequest, NotFound

MAX_BYTES = 10 * 1024 * 1024
MAX_DOCUMENTS = 5
MAX_PAGES = 5
TYPES = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    chars = []
    for c in value:
        if c.isdecimal():
            chars.append(str(unicodedata.decimal(c)))
        else:
            chars.append(c if unicodedata.category(c)[0] in "LNM" else " ")
    return " ".join("".join(chars).split())


def private_path(name: str) -> Path:
    root = Path(settings.private_upload_dir).resolve()
    if Path(name).name != name:
        raise NotFound("Document not found")
    return root / name


def documents(db, prop_id: int):
    return db.query(PropertyDocument).filter_by(property_id=prop_id).order_by(PropertyDocument.id).all()


def summary(db, prop: Property) -> dict:
    rows = documents(db, prop.id)
    result = [{"id": d.id, "name": d.original_name, "processed": d.processed,
               "url": f"/api/properties/{prop.id}/documents/{d.id}"} for d in rows]
    # Old documents remain available only through an authenticated download route.
    for url in prop.documents or []:
        if url.startswith("/uploads/") and Path(url).name == url.removeprefix("/uploads/"):
            result.append({"id": "legacy:" + Path(url).name, "name": "Previously uploaded document",
                           "processed": False, "url": f"/api/properties/{prop.id}/documents/legacy/{Path(url).name}"})
    return {"property_id": prop.id, "status": prop.document_check_status,
            "reasons": prop.document_check_reasons, "checked_at": prop.document_checked_at,
            "listing_status": prop.status.value, "documents": result}


def register_document(db, prop: Property, data: bytes, content_type: str, name: str) -> PropertyDocument:
    from services import women_safety
    prop = women_safety.locked(db, prop.id)
    if content_type not in TYPES:
        raise BadRequest("Upload a PDF, JPEG, PNG, or WebP document")
    if not data or len(data) > MAX_BYTES:
        raise BadRequest("Documents must be between 1 byte and 10 MB")
    magic_ok = {
        "application/pdf": data.startswith(b"%PDF-"),
        "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": data.startswith(b"\xff\xd8\xff"),
        "image/webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP",
    }[content_type]
    if not magic_ok:
        raise BadRequest("The document contents do not match its file type")
    if len(documents(db, prop.id)) >= MAX_DOCUMENTS:
        raise BadRequest("Up to five documents are allowed; remove an old document before replacing it")
    name = Path(name.replace("\\", "/")).name[:255] or "document" + TYPES[content_type]
    stored = uuid.uuid4().hex + TYPES[content_type]
    path = private_path(stored)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    doc = PropertyDocument(property_id=prop.id, stored_name=stored, original_name=name,
                           content_type=content_type, content_hash=hashlib.sha256(data).hexdigest())
    db.add(doc)
    if prop.is_female_only:
        women_safety.invalidate(db, prop)
    prop.document_check_status = "checking"
    prop.document_check_reasons = ["Document checks are running"]
    prop.document_checked_at = None
    prop.status = ListingStatus.pending
    enqueue_index(db, "listing", prop.id)
    enqueue(db, "verify_documents", {"property_id": prop.id}, dedupe_key=f"verify:{prop.id}")
    db.commit()
    db.refresh(doc)
    return doc


def _run(args: list[str], timeout: int = 30) -> str:
    result = subprocess.run(args, capture_output=True, timeout=timeout, check=True)
    return result.stdout.decode("utf-8", errors="replace")


def _ocr(path: Path) -> str:
    tsv = _run(["tesseract", str(path), "stdout", "-l", "eng+ben", "--psm", "3", "tsv"])
    words = [r for r in csv.DictReader(io.StringIO(tsv), delimiter="\t") if r.get("text", "").strip()]
    confidence = [float(r["conf"]) for r in words if float(r.get("conf", -1)) >= 0]
    if not confidence or sum(confidence) / len(confidence) < 65:
        raise ValueError("The scan is unclear; upload a sharper image or request manual review")
    return " ".join(r["text"] for r in words)


def extract_text(path: Path, content_type: str) -> str:
    if content_type != "application/pdf":
        return _ocr(path)[:30000]
    from pypdf import PdfReader
    reader = PdfReader(path)
    if reader.is_encrypted:
        raise ValueError("Password-protected documents require manual review")
    if not 1 <= len(reader.pages) <= MAX_PAGES:
        raise ValueError("Upload a document of one to five pages")
    parts = []
    with tempfile.TemporaryDirectory(dir=path.parent) as temp:
        for i, page in enumerate(reader.pages):
            text = (page.extract_text() or "")[:30000]
            if len(normalize(text)) < 40:
                prefix = str(Path(temp) / f"page-{i}")
                _run(["pdftoppm", "-f", str(i + 1), "-l", str(i + 1), "-singlefile", "-scale-to", "2200",
                      "-png", str(path), prefix])
                text = _ocr(Path(prefix + ".png"))
            parts.append(text)
    return "\n".join(parts)[:30000]


def _contains(text: str, value: str) -> bool:
    value = normalize(value)
    return len(value) >= 3 and f" {value} " in f" {text} "


def check_fields(prop: Property, account_name: str, text: str) -> list[str]:
    text = normalize(text)
    failures = []
    if len(text) < 40:
        failures.append("Not enough readable document text")
    if not _contains(text, account_name) or not _contains(text, prop.owner_name):
        failures.append("The document must match both the account holder and the listed owner name")
    generic = {"road", "rd", "house", "flat", "block", "plot", "floor", "apartment", "no", "the", "at", "in",
               "রোড", "বাসা", "ব্লক", "ফ্ল্যাট", "নং", "নম্বর"}
    tokens = {t for t in normalize(prop.address).split() if t not in generic}
    numeric = {t for t in tokens if t.isdecimal()}
    matched = {t for t in tokens if f" {t} " in f" {text} "}
    if (len(tokens) < 2 or not numeric or not tokens <= matched
            or not _contains(text, prop.area)):
        failures.append("The property address, building/road number, and area could not be matched reliably")
    kinds = ("deed", "ownership", "landlord", "tenancy", "rental agreement", "lease", "দলিল", "মালিক", "চুক্তি", "খতিয়ান")
    if not any(normalize(k) in text for k in kinds):
        failures.append("A recognizable ownership or tenancy document is required")
    return failures


def evaluate(db, prop: Property) -> None:
    from services.publication import safety_ready
    rows = documents(db, prop.id)
    if any(not d.processed for d in rows):
        prop.document_check_status = "checking"
        return
    failures = []
    owner = db.get(User, prop.owner_id) if prop.owner_id else None
    if not rows:
        failures.append("Upload an ownership or tenancy document to begin checks")
    if not owner:
        failures.append("The listing is not linked to an owner account")
    for doc in rows:
        if doc.extraction_error:
            failures.append(doc.extraction_error)
        else:
            failures.extend(check_fields(prop, owner.name if owner else "", doc.extracted_text or ""))
        hashes = [PropertyDocument.content_hash == doc.content_hash]
        if doc.text_hash:
            hashes.append(PropertyDocument.text_hash == doc.text_hash)
        reused = (db.query(PropertyDocument.id).join(Property, Property.id == PropertyDocument.property_id)
                  .filter(or_(*hashes), or_(Property.owner_id != prop.owner_id, Property.owner_id.is_(None)))
                  .first())
        if reused:
            failures.append("This document was also submitted by another owner account; admin review is required")
    prop.document_check_status = "needs_review" if failures else "passed"
    prop.document_check_reasons = list(dict.fromkeys(failures)) if failures else [
        "Readable document, matching owner and address, and no reuse by another account found"]
    prop.document_checked_at = datetime.now(timezone.utc)
    prop.status = ListingStatus.pending if failures or prop.moderation_reason or not safety_ready(prop) else ListingStatus.active
    enqueue_index(db, "listing", prop.id)
    if prop.status == ListingStatus.active:
        enqueue(db, "screen_listing", {"property_id": prop.id}, dedupe_key=f"screen:{prop.id}")


def verify_documents(db, property_id: int) -> dict:
    prop = db.get(Property, property_id)
    if not prop:
        return {"skipped": "listing removed"}
    for doc in documents(db, property_id):
        if doc.processed:
            continue
        try:
            doc.extracted_text = extract_text(private_path(doc.stored_name), doc.content_type)
            doc.text_hash = hashlib.sha256(normalize(doc.extracted_text).encode()).hexdigest()
            doc.extraction_error = None
        except (FileNotFoundError, subprocess.SubprocessError):
            doc.extraction_error = "Local OCR could not finish; admin review or a clearer document is required"
        except Exception:
            doc.extraction_error = "The document could not be read safely; upload a readable PDF/image or request admin review"
        doc.processed = True
    db.flush()
    # Evaluate against the latest listing data, serialized with edits/uploads and admin decisions.
    prop = db.query(Property).filter_by(id=property_id).with_for_update().populate_existing().first()
    if prop and prop.document_check_status not in ("reviewed", "rejected"):
        evaluate(db, prop)
    db.commit()
    return {"status": prop.document_check_status if prop else "removed"}


def invalidate(db, prop: Property) -> None:
    prop.status = ListingStatus.pending
    prop.document_check_status = "checking" if documents(db, prop.id) else "not_submitted"
    prop.document_check_reasons = ["Listing details changed; document checks must run again"]
    prop.document_checked_at = None
    enqueue(db, "verify_documents", {"property_id": prop.id}, dedupe_key=f"verify:{prop.id}")


def remove_document(db, prop: Property, doc: PropertyDocument) -> None:
    from services import women_safety
    prop = women_safety.locked(db, prop.id)
    if prop.is_female_only:
        women_safety.invalidate(db, prop)
    db.delete(doc)
    db.flush()
    evaluate(db, prop)
    db.commit()
    private_path(doc.stored_name).unlink(missing_ok=True)
