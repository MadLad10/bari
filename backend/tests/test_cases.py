from alembic import command
from alembic.config import Config

from models import CaseUpdate, ForumPost, InvestigationCase, PostType, Property
from tests.conftest import BACKEND, make_user
from tests.test_bookings import _booking


def payload(**changes):
    return {"category": "other", "title": "Please investigate this concern", "description": "I need an admin to look into the details of this report.", **changes}


def open_case(client, headers, **changes):
    result = client.post("/api/cases", headers=headers, json=payload(**changes))
    assert result.status_code == 201, result.text
    return result.json()


def decision(client, admin, row, status, **changes):
    return client.patch(f"/api/admin/cases/{row['id']}", headers=admin,
                        json={"status": status, "message": "We are reviewing the details of this case.",
                              "expected_version": row["version"], **changes})


def test_case_privacy_and_admin_only_operations(client, db, renter, owner, admin):
    row = open_case(client, renter)
    assert client.get("/api/cases/mine").status_code == 401
    assert client.get(f"/api/cases/{row['id']}").status_code == 401
    assert client.get(f"/api/cases/{row['id']}", headers=owner).status_code == 403
    assert client.get("/api/cases/mine", headers=owner).json() == []
    for operation, body in [("claim", {"expected_version": 1}), ("notes", {"body": "Private", "internal": True})]:
        assert client.post(f"/api/admin/cases/{row['id']}/{operation}", headers=renter, json=body).status_code == 403
    assert decision(client, renter, row, "investigating").status_code == 403
    assert client.get("/api/admin/cases", headers=renter).status_code == 403
    assert client.get("/api/admin/cases", headers=admin).json()[0]["reporter_name"] == "Rafi Renter"
    assert "reporter_id" not in client.get(f"/api/cases/{row['id']}", headers=renter).json()
    assert client.post("/api/cases", headers=renter, json=payload(reporter_id=999)).status_code == 422


def test_reporter_feedback_internal_notes_and_resolution_lifecycle(client, renter, admin):
    row = open_case(client, renter)
    assigned = client.post(f"/api/admin/cases/{row['id']}/claim", headers=admin,
                           json={"expected_version": row["version"]}).json()
    assert assigned["assigned_name"] == "Admin"
    row = decision(client, admin, assigned, "investigating").json()
    note = client.post(f"/api/admin/cases/{row['id']}/notes", headers=admin,
                      json={"body": "INTERNAL: check the listing owner's account history", "internal": True}).json()
    assert any(u["internal"] for u in note["updates"])
    public = client.get(f"/api/cases/{row['id']}", headers=renter).json()
    assert all(not u["internal"] for u in public["updates"])
    assert "INTERNAL" not in str(public)
    assert "INTERNAL" not in str(client.get("/api/cases/mine", headers=renter).json())
    row = decision(client, admin, note, "awaiting_reporter", message="Please tell us the date of the incident.").json()
    replied = client.post(f"/api/cases/{row['id']}/messages", headers=renter, json={"body": "It happened on Saturday afternoon."}).json()
    assert replied["status"] == "investigating"
    assert decision(client, admin, replied, "resolved", message="short").status_code == 400
    closed = decision(client, admin, replied, "resolved", message="We investigated and the listing details have been corrected.").json()
    assert closed["status"] == "resolved" and closed["resolved_at"]
    assert closed["resolution"] == "We investigated and the listing details have been corrected."
    seen = client.get(f"/api/cases/{row['id']}", headers=renter).json()
    assert seen["resolution"] == closed["resolution"] and "INTERNAL" not in str(seen)
    assert client.post(f"/api/cases/{row['id']}/messages", headers=renter, json={"body": "Another detail"}).status_code == 409
    reopened = decision(client, admin, closed, "investigating", message="Reopening to review additional information.").json()
    assert reopened["status"] == "investigating" and reopened["resolution"] is None and reopened["resolved_at"] is None


def test_public_admin_messages_and_note_injection_denied(client, renter, admin):
    row = open_case(client, renter)
    assert client.post(f"/api/cases/{row['id']}/messages", headers=renter, json={"body": "Make this secret", "internal": True}).status_code == 422
    result = client.post(f"/api/admin/cases/{row['id']}/notes", headers=admin,
                         json={"body": "We have received your evidence.", "internal": False})
    assert result.status_code == 200
    assert "We have received your evidence." in str(client.get(f"/api/cases/{row['id']}", headers=renter).json())


def test_invalid_transitions_and_stale_admin_decisions(client, renter, admin):
    row = open_case(client, renter)
    assert decision(client, admin, row, "resolved").status_code == 409
    investigating = decision(client, admin, row, "investigating").json()
    assert decision(client, admin, row, "dismissed").status_code == 409
    assert decision(client, admin, investigating, "open").status_code == 409
    dismissed = decision(client, admin, investigating, "dismissed", message="The submitted information does not establish a listing issue.").json()
    assert dismissed["resolution"] and dismissed["status"] == "dismissed"


def test_forum_reports_create_cases_even_when_not_flagged(client, db, renter, admin):
    result = client.post("/api/forum/", headers=renter, json={"title": "Please review the address", "body": "The details shown on this listing need investigation.", "post_type": "report"})
    assert result.status_code == 201, result.text
    case_id = result.json()["case_id"]
    assert case_id
    record = db.get(InvestigationCase, case_id)
    assert record.forum_post_id == result.json()["id"]
    assert record.category == "forum_report"
    assert client.get("/api/admin/cases", headers=admin).json()[0]["id"] == case_id
    assert client.get("/api/cases/mine", headers=renter).json()[0]["id"] == case_id
    assert "case_id" not in client.get(f"/api/forum/{result.json()['id']}").json() or client.get(f"/api/forum/{result.json()['id']}").json()["case_id"] is None


def test_holding_listing_is_explicit_and_cannot_be_self_published(client, make_property, renter, owner, admin):
    prop = make_property()
    row = open_case(client, renter, category="unsafe_listing", property_id=prop["id"])
    assert client.get(f"/api/properties/{prop['id']}").status_code == 200
    held = decision(client, admin, row, "investigating", hold_listing=True).json()
    assert held["status"] == "investigating"
    assert client.get(f"/api/properties/{prop['id']}").status_code == 404
    assert client.put(f"/api/properties/{prop['id']}", headers=owner, json={"status": "active"}).status_code == 403
    assert client.put(f"/api/properties/{prop['id']}", headers=admin, json={"status": "active"}).status_code == 403
    assert client.post(f"/api/admin/listings/{prop['id']}/approve", headers=admin).status_code == 400
    resolved = decision(client, admin, held, "resolved", message="We reviewed the concern and approved the corrected information.")
    assert resolved.status_code == 200
    assert client.get(f"/api/properties/{prop['id']}").status_code == 404
    assert client.post(f"/api/admin/listings/{prop['id']}/approve", headers=admin).status_code == 200


def test_booking_dispute_requires_a_related_booking(client, db, make_property, renter, owner):
    prop = make_property()
    booking = client.post("/api/bookings/", headers=renter, json=_booking(prop["id"])).json()
    _, outsider = make_user(db, "renter")
    assert client.post("/api/cases", headers=outsider, json=payload(category="booking_dispute", booking_id=booking["id"])).status_code == 403
    row = open_case(client, renter, category="booking_dispute", booking_id=booking["id"])
    assert row["property_id"] == prop["id"] and row["booking_reference"] == booking["id"]
    assert open_case(client, owner, category="booking_dispute", booking_id=booking["id"])["id"] != row["id"]
    other = make_property(title="Different property for a validation check")
    assert client.post("/api/cases", headers=renter, json=payload(category="booking_dispute", booking_id=booking["id"], property_id=other["id"])).status_code == 400


def test_cases_keep_snapshots_after_listing_is_deleted(client, db, make_property, owner, renter):
    prop = make_property()
    row = open_case(client, renter, category="unsafe_listing", property_id=prop["id"])
    assert client.delete(f"/api/properties/{prop['id']}", headers=owner).status_code == 204
    history = client.get(f"/api/cases/{row['id']}", headers=renter).json()
    assert history["property_id"] is None
    assert history["property_title"] == prop["title"]
    assert history["description"] == row["description"]


def test_case_input_validation_filters_and_paging(client, renter, admin):
    for data in (payload(title="     "), payload(category="unsafe_listing"), payload(category="booking_dispute"), payload(property_id=999999)):
        assert client.post("/api/cases", headers=renter, json=data).status_code in (400, 404, 422)
    first = open_case(client, renter, title="First concern for the queue")
    second = open_case(client, renter, title="Second concern for the queue")
    decision(client, admin, first, "dismissed", message="No further investigation is required for this concern.")
    assert len(client.get("/api/admin/cases?status=open", headers=admin).json()) == 1
    assert client.get("/api/admin/cases?q=Second", headers=admin).json()[0]["id"] == second["id"]
    assert len(client.get("/api/cases/mine?limit=1&skip=1", headers=renter).json()) == 1


def test_migration_backfills_existing_reports_without_guessing_an_account(client, db, renter):
    old = ForumPost(title="Legacy unsafe listing report", body="An older report waiting to be investigated.",
                    post_type=PostType.report, author_name="Legacy Reporter", author_id=None)
    db.add(old); db.commit(); old_id = old.id
    db.close()
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.downgrade(config, "b825c73e0a41")
    command.upgrade(config, "head")
    row = db.query(InvestigationCase).filter_by(forum_post_id=old_id).one()
    assert row.reporter_id is None and row.reporter_name == "Legacy Reporter"
    assert db.query(CaseUpdate).filter_by(case_id=row.id).count() == 1
    assert client.get("/api/cases/mine", headers=renter).json() == []
