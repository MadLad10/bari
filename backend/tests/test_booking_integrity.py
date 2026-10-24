from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from agent import tools as agent_tools
from models import Booking, BookingStatus, PendingAction, Property
from services.bookings import compute_price
from services.errors import BadRequest
from tests.conftest import make_user
from tests.test_bookings import _booking


def quote_body(body):
    return {key: body[key] for key in ("property_id", "check_in", "check_out", "rental_type")}


@pytest.mark.parametrize("period,requested", [("daily", "monthly"), ("hourly", "daily"), ("monthly", "hourly")])
def test_billing_period_cannot_be_changed_in_quote_or_booking(client, db, make_property, renter, period, requested):
    prop = make_property(rental_type=period, price=1500)
    body = _booking(prop["id"], rental_type=requested)
    for endpoint, payload in (("/api/bookings/quote", quote_body(body)), ("/api/bookings/", body)):
        result = client.post(endpoint, json=payload, headers=renter)
        assert result.status_code == 400, result.text
        assert "billing period" in result.json()["detail"]
    assert db.query(Booking).count() == 0


def test_sale_listing_cannot_be_quoted_or_booked_as_a_rental(client, db, make_property, renter):
    prop = make_property(listing_type="sale", rental_type=None)
    body = _booking(prop["id"])
    for endpoint, payload in (("/api/bookings/quote", quote_body(body)), ("/api/bookings/", body)):
        result = client.post(endpoint, headers=renter, json=payload)
        assert result.status_code == 400
        assert "Sale listings" in result.json()["detail"]
    assert db.query(Booking).count() == 0


@pytest.mark.parametrize("start_days,nights", [(-100, 1), (-1, 3), (1, 0), (1, -1)])
def test_past_or_reversed_dates_cannot_be_quoted_or_booked(client, db, make_property, renter, start_days, nights):
    prop = make_property()
    body = _booking(prop["id"], start_days=start_days, nights=nights)
    for endpoint, payload in (("/api/bookings/quote", quote_body(body)), ("/api/bookings/", body)):
        assert client.post(endpoint, headers=renter, json=payload).status_code == 400
    assert db.query(Booking).count() == 0


@pytest.mark.parametrize("field", ["check_in", "check_out"])
def test_timezone_is_required_at_api_and_service_boundaries(client, db, make_property, renter, field):
    prop = make_property()
    body = _booking(prop["id"])
    body[field] = datetime.fromisoformat(body[field]).replace(tzinfo=None).isoformat()
    for endpoint, payload in (("/api/bookings/quote", quote_body(body)), ("/api/bookings/", body)):
        assert client.post(endpoint, headers=renter, json=payload).status_code == 422
    with pytest.raises(BadRequest, match="timezone"):
        compute_price(db.get(Property, prop["id"]), datetime.fromisoformat(body["check_in"]),
                      datetime.fromisoformat(body["check_out"]), "monthly")


def test_valid_hourly_price_uses_absolute_time_across_offsets(client, make_property, renter):
    prop = make_property(rental_type="hourly", price=1000)
    start = (datetime.now(timezone.utc) + timedelta(days=10)).replace(hour=0, minute=0, second=0, microsecond=0)
    body = {**_booking(prop["id"], rental_type="hourly"),
            "check_in": start.astimezone(timezone(timedelta(hours=6))).isoformat(),
            "check_out": (start + timedelta(minutes=90)).astimezone(timezone(timedelta(hours=-5))).isoformat()}
    quote = client.post("/api/bookings/quote", json=quote_body(body))
    created = client.post("/api/bookings/", headers=renter, json=body)
    assert quote.status_code == 200 and created.status_code == 201
    assert quote.json()["total_price"] == created.json()["total_price"] == 1500


@pytest.mark.parametrize("scenario", ["period", "sale", "past"])
def test_ai_price_and_draft_follow_the_same_booking_rules(db, make_property, scenario):
    prop = make_property(rental_type="daily", listing_type="sale" if scenario == "sale" else "rent")
    args = {"property_id": prop["id"], "check_in": "2000-01-01" if scenario == "past" else "2030-01-01",
            "check_out": "2000-02-01" if scenario == "past" else "2030-02-01",
            "rental_type": "monthly" if scenario == "period" else "daily"}
    ctx = agent_tools.ToolContext(user_id=1, request_id="booking-integrity-test", last_user_message="Please book this property")
    with pytest.raises(agent_tools.ToolError):
        agent_tools.compute_price(db, ctx, agent_tools.PriceArgs(**args))
    with pytest.raises(agent_tools.ToolError):
        agent_tools.draft_booking(db, ctx, agent_tools.DraftBookingArgs(**args))
    if scenario in ("sale", "past"):
        with pytest.raises(agent_tools.ToolError):
            agent_tools.check_availability(db, ctx, agent_tools.AvailabilityArgs(**args))
    assert db.query(PendingAction).count() == 0 and db.query(Booking).count() == 0


def test_ai_confirmation_rechecks_period_after_owner_changes_listing(client, db, make_property):
    user, headers = make_user(db, "renter")
    prop = make_property(rental_type="daily")
    ctx = agent_tools.ToolContext(user_id=user.id, request_id="draft-period-test", last_user_message="Please book this property")
    action = agent_tools.draft_booking(db, ctx, agent_tools.DraftBookingArgs(
        property_id=prop["id"], check_in="2030-01-01", check_out="2030-02-01"))
    db.get(Property, prop["id"]).rental_type = "monthly"
    db.commit()
    result = client.post(f"/api/actions/{action['pending_action_id']}/confirm", headers=headers, json={"renter_phone": "01811000000"})
    assert result.status_code == 400, result.text
    assert db.query(Booking).count() == 0
    assert db.get(PendingAction, action["pending_action_id"]).status == "failed"


@pytest.mark.parametrize("state", [BookingStatus.confirmed, BookingStatus.pending, BookingStatus.cancelled])
def test_archiving_retains_history_and_database_prevents_hard_delete(client, db, make_property, owner, renter, admin, state):
    prop = make_property()
    result = client.post("/api/bookings/", headers=renter, json=_booking(prop["id"]))
    assert result.status_code == 201
    booked = result.json()
    original = db.get(Booking, booked["id"])
    original.check_in = datetime.now(timezone.utc) - timedelta(days=30)
    original.check_out = original.check_in + timedelta(days=2)
    original.status = state
    if state == BookingStatus.cancelled:
        original.cancellation_reason = "renter_cancelled"
        original.cancelled_at = datetime.now(timezone.utc) - timedelta(days=40)
    db.commit()
    assert client.delete(f"/api/properties/{prop['id']}", headers=owner).status_code == 204
    db.expire_all()
    archived = db.get(Property, prop["id"])
    assert archived.archived_at and archived.status.value == "inactive"
    for headers in ({}, owner, renter):
        assert client.get(f"/api/properties/{prop['id']}", headers=headers).status_code == 404
    assert client.get("/api/properties/mine", headers=owner).json() == []
    assert client.get("/api/properties/count").json()["count"] == 0
    assert client.get("/api/properties/map").json()["total"] == 0
    for endpoint, headers in (("/api/bookings/mine", renter), ("/api/bookings/owner", owner)):
        history = client.get(endpoint, headers=headers).json()
        assert len(history) == 1 and history[0]["id"] == booked["id"]
        assert history[0]["property"]["title"] == prop["title"]
        assert history[0]["property"]["archived_at"]
        assert history[0]["total_price"] == booked["total_price"]
        assert history[0]["status"] == state.value
    detail = client.get(f"/api/bookings/{booked['id']}", headers=renter)
    assert detail.status_code == 200 and detail.json()["property"]["address"] == prop["address"]
    _, outsider = make_user(db, "renter")
    assert client.get(f"/api/bookings/{booked['id']}", headers=outsider).status_code == 403
    assert client.put(f"/api/properties/{prop['id']}", headers=owner, json={"status": "active"}).status_code == 404
    assert client.post(f"/api/admin/listings/{prop['id']}/approve", headers=admin).status_code == 404
    with pytest.raises(IntegrityError):
        db.execute(delete(Property).where(Property.id == prop["id"]))
        db.commit()
    db.rollback()
    assert db.get(Booking, booked["id"]) is not None


def test_cancelled_future_booking_history_and_disputes_survive_archiving(client, db, make_property, owner, renter):
    prop = make_property()
    booked = client.post("/api/bookings/", headers=renter, json=_booking(prop["id"])).json()
    assert client.delete(f"/api/properties/{prop['id']}", headers=owner).status_code == 409
    assert client.patch(f"/api/bookings/{booked['id']}/cancel", headers=renter).status_code == 200
    assert client.delete(f"/api/properties/{prop['id']}", headers=owner).status_code == 204
    detail = client.get(f"/api/bookings/{booked['id']}", headers=renter).json()
    assert detail["cancellation_reason"] == "renter_cancelled" and detail["cancelled_at"]
    response = client.post("/api/cases", headers=renter, json={"category": "booking_dispute", "booking_id": booked["id"],
        "title": "Dispute about an archived rental", "description": "Please investigate the issue with my previous booking of this property."})
    assert response.status_code == 201, response.text
    assert response.json()["property_id"] == prop["id"]


def test_pending_request_cannot_be_accepted_after_listing_becomes_sale(client, db, make_property, owner, renter):
    prop = make_property()
    booked = client.post("/api/bookings/", headers=renter, json=_booking(prop["id"])).json()
    db.get(Property, prop["id"]).listing_type = "sale"
    db.commit()
    assert client.patch(f"/api/bookings/{booked['id']}/accept", headers=owner).status_code == 400
    assert client.get(f"/api/bookings/{booked['id']}", headers=renter).json()["status"] == "pending"
