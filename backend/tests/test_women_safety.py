import pytest

from models import ListingStatus, Property, WomenSafetyReview
from rag.indexer import build_chunks, index_source
from services import verification
from services.women_safety import ADMIN_CHECKS, OWNER_CHECKS
from tests.conftest import make_user, property_payload
from tests.test_bookings import _booking
from tests.test_verification import document_pdf, TEXT


def draft(client, owner):
    res = client.post("/api/properties/", headers=owner, json=property_payload(is_female_only=True))
    assert res.status_code == 201, res.text
    return res.json()["id"]


def state(client, pid, headers):
    res = client.get(f"/api/properties/{pid}/women-safety", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def submit(client, pid, owner, **overrides):
    data = {"expected_version": state(client, pid, owner)["version"],
            "checklist": dict.fromkeys(OWNER_CHECKS, True),
            "notes": "Women-only occupancy, working locks and lighting, private bathrooms and a resident emergency contact."}
    return client.post(f"/api/properties/{pid}/women-safety", headers=owner, json={**data, **overrides})


def decide(client, pid, admin, verdict="approved", **overrides):
    data = {"expected_version": state(client, pid, admin)["version"], "verdict": verdict,
            "checklist": dict.fromkeys(ADMIN_CHECKS, True),
            "notes": "Reviewed owner documents, photo evidence and occupancy policy; checked emergency arrangements with owner."}
    return client.post(f"/api/admin/women-safety/{pid}", headers=admin, json={**data, **overrides})


def reviewed_documents(db, pid):
    prop = db.get(Property, pid)
    prop.document_check_status = "reviewed"
    db.commit()


def test_owner_flag_and_generic_admin_approval_do_not_grant_safety(client, db, owner, admin):
    pid = draft(client, owner)
    assert state(client, pid, owner)["status"] == "not_submitted"
    reviewed_documents(db, pid)
    res = client.post(f"/api/admin/listings/{pid}/approve", headers=admin)
    assert res.status_code == 200 and res.json()["status"] == "pending"
    for headers in (owner, admin):
        assert client.put(f"/api/properties/{pid}", headers=headers, json={"status": "active"}).status_code == 403
    assert client.get("/api/properties/?is_female_only=true").json() == []
    assert client.get(f"/api/properties/{pid}").status_code == 404
    assert decide(client, pid, admin).status_code == 400


def test_private_request_permissions_and_no_self_review(client, db, owner, renter, admin):
    pid = draft(client, owner)
    _, other_owner = make_user(db, "owner")
    for headers, code in (({}, 401), (renter, 403), (other_owner, 403)):
        assert client.get(f"/api/properties/{pid}/women-safety", headers=headers).status_code == code
        assert submit_request(client, pid, headers).status_code == code
    assert client.get("/api/admin/women-safety", headers=owner).status_code == 403
    assert submit(client, pid, owner, checklist={}).status_code == 400
    assert submit(client, pid, owner, notes=" ").status_code == 422
    assert submit(client, pid, owner).status_code == 200
    assert decide(client, pid, owner).status_code == 403
    prop = db.get(Property, pid)
    admin_user, _ = make_user(db, "admin")
    prop.owner_id = admin_user.id
    db.commit()
    from services.users import create_token
    own_admin = {"Authorization": f"Bearer {create_token(admin_user)}"}
    assert decide(client, pid, own_admin).status_code == 403


def submit_request(client, pid, headers):
    return client.post(f"/api/properties/{pid}/women-safety", headers=headers, json={
        "expected_version": 0, "checklist": dict.fromkeys(OWNER_CHECKS, True), "notes": "Working locks, lights, privacy and emergency contact arrangements."})


def test_changes_resubmit_approval_and_audit(client, db, owner, admin):
    pid = draft(client, owner)
    assert submit(client, pid, owner).status_code == 200
    assert submit(client, pid, owner).status_code == 400
    assert decide(client, pid, admin).status_code == 400  # ownership remains an independent prerequisite
    reviewed_documents(db, pid)
    assert decide(client, pid, admin, checklist={}).status_code == 400
    assert decide(client, pid, admin, "changes_requested").status_code == 200
    feedback = state(client, pid, owner)
    assert feedback["status"] == "changes_requested" and feedback["history"][0]["notes"]
    assert submit(client, pid, owner).status_code == 200
    queue = client.get("/api/admin/women-safety", headers=admin).json()
    assert queue["total"] == 1 and queue["items"][0]["property_id"] == pid
    approved = decide(client, pid, admin)
    assert approved.status_code == 200, approved.text
    assert approved.json()["listing_status"] == "active"
    public = client.get(f"/api/properties/{pid}").json()
    assert public["women_safety_status"] == "approved" and public["women_safety_reviewed_at"]
    assert "women_safety_submission" not in public and "history" not in public
    assert client.get("/api/properties/?is_female_only=true").json()[0]["id"] == pid
    assert len(state(client, pid, owner)["history"]) == 2
    row = db.query(WomenSafetyReview).filter_by(property_id=pid, verdict="approved").one()
    assert row.submission["listing_snapshot"]["address"] == public["address"]


@pytest.mark.parametrize("changes", [{"description": "Changed access controls and occupancy details requiring fresh review."},
                                      {"owner_phone": "01811000009"}, {"amenities": ["New shared entrance"]}])
def test_safety_edits_revoke_and_stale_review_fails(client, db, owner, admin, changes):
    pid = draft(client, owner)
    reviewed_documents(db, pid)
    submit(client, pid, owner)
    old_version = state(client, pid, owner)["version"]
    assert client.put(f"/api/properties/{pid}", headers=owner, json=changes).status_code == 200
    assert decide(client, pid, admin, expected_version=old_version).status_code == 409
    submit(client, pid, owner)
    assert decide(client, pid, admin).status_code == 200
    assert client.put(f"/api/properties/{pid}", headers=owner, json={"price": 13000}).json()["women_safety_status"] == "approved"
    # Relevant edits invalidate approval even if a status update is bundled with them.
    res = client.put(f"/api/properties/{pid}", headers=owner, json={"title": "Updated room details near campus", "status": "active"})
    assert res.json()["status"] == "pending" and res.json()["women_safety_status"] == "not_submitted"
    assert client.get(f"/api/properties/{pid}").status_code == 404


def test_revoke_and_preserve_owner_pause(client, db, owner, admin):
    pid = draft(client, owner)
    reviewed_documents(db, pid)
    client.put(f"/api/properties/{pid}", headers=owner, json={"status": "inactive"})
    submit(client, pid, owner)
    assert decide(client, pid, admin).json()["listing_status"] == "inactive"
    assert client.put(f"/api/properties/{pid}", headers=owner, json={"status": "active"}).status_code == 200
    assert decide(client, pid, admin, "rejected").json()["listing_status"] == "pending"
    assert state(client, pid, owner)["document_check_status"] == "reviewed"
    assert client.put(f"/api/properties/{pid}", headers=owner, json={"status": "active"}).status_code == 403


def test_active_status_cannot_bypass_public_search_booking_or_index(client, db, owner, renter):
    pid = draft(client, owner)
    prop = db.get(Property, pid)
    prop.status = ListingStatus.active
    prop.document_check_status = "reviewed"
    db.commit()
    assert client.get(f"/api/properties/{pid}").status_code == 404
    assert client.get("/api/properties/count").json()["count"] == 0
    assert client.get("/api/properties/").json() == []
    assert client.post("/api/bookings/", headers=renter, json=_booking(pid)).status_code == 409
    assert build_chunks(db, "listing", pid) == []


def test_automatic_document_checks_do_not_approve_safety(client, db, owner, tmp_path, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "private_upload_dir", str(tmp_path))
    pid = client.post("/api/properties/", headers=owner, json=property_payload(
        is_female_only=True, owner_name="Karim Owner", address="House 12, Green Road, Dhanmondi", area="Dhanmondi")).json()["id"]
    assert client.post(f"/api/properties/{pid}/documents", headers=owner,
                       files={"file": ("tenancy.pdf", document_pdf(TEXT), "application/pdf")}).status_code == 200
    assert verification.verify_documents(db, pid)["status"] == "passed"
    assert state(client, pid, owner)["listing_status"] == "pending"
    assert state(client, pid, owner)["status"] == "not_submitted"


def test_open_investigation_prevents_safety_approval(client, db, owner, admin, renter):
    from models import InvestigationCase
    pid = draft(client, owner)
    reviewed_documents(db, pid)
    submit(client, pid, owner)
    reporter, _ = make_user(db, "renter")
    db.add(InvestigationCase(reporter_id=reporter.id, reporter_name=reporter.name, title="Unsafe property report",
                             description="Safety arrangements need investigating before approval.", category="unsafe_listing",
                             property_id=pid, status="open"))
    db.commit()
    assert decide(client, pid, admin).status_code == 400


def test_stale_search_chunks_and_agent_reads_cannot_bypass_review(client, db, make_property):
    from agent.tools import ToolError, _active_property
    from rag.hybrid import hybrid_search
    prop = make_property(is_female_only=True)
    pid = prop["id"]
    index_source(db, "listing", pid)
    row = db.get(Property, pid)
    row.women_safety_status = "changes_requested"
    db.commit()  # simulate delayed indexing while the old vectors remain
    assert hybrid_search(db, "Furnished flat near BRAC", sources=("listing",)).hits == []
    with pytest.raises(ToolError):
        _active_property(db, pid)


def test_replacing_photos_or_documents_invalidates_safety(client, db, owner, admin, tmp_path, monkeypatch):
    import routers.properties
    from config import settings
    monkeypatch.setattr(routers.properties, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "private_upload_dir", str(tmp_path / "private"))
    pid = draft(client, owner)
    reviewed_documents(db, pid)
    submit(client, pid, owner)
    decide(client, pid, admin)
    photo = client.post(f"/api/properties/{pid}/photos", headers=owner,
                        files={"file": ("entrance.png", b"\x89PNG\r\n\x1a\nexample", "image/png")})
    assert photo.status_code == 200
    result = state(client, pid, owner)
    assert result["status"] == "not_submitted" and result["listing_status"] == "pending"
    assert result["document_check_status"] == "reviewed"
    submit(client, pid, owner)
    decide(client, pid, admin)
    doc = client.post(f"/api/properties/{pid}/documents", headers=owner,
                      files={"file": ("replacement.pdf", document_pdf(TEXT), "application/pdf")})
    assert doc.status_code == 200
    result = state(client, pid, owner)
    assert result["status"] == "not_submitted" and result["listing_status"] == "pending"
    assert len(result["history"]) == 2
