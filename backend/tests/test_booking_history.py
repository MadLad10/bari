from datetime import datetime, timedelta, timezone

from models import Booking, BookingStatus, ListingStatus, Property
from tests.conftest import make_user
from tests.test_bookings import _booking


def test_history_is_private_includes_all_states_and_safe_property_details(client, db, make_property, owner, renter):
    prop = make_property()
    first = client.post("/api/bookings/", headers=renter, json=_booking(prop["id"])).json()
    second = client.post("/api/bookings/", headers=renter, json=_booking(prop["id"], start_days=90)).json()
    client.patch(f"/api/bookings/{first['id']}/decline", headers=owner)
    client.patch(f"/api/bookings/{second['id']}/accept", headers=owner)
    _, other = make_user(db, "renter")
    assert client.get("/api/bookings/mine").status_code == 401
    assert client.get("/api/bookings/mine", headers=other).json() == []
    assert client.get(f"/api/bookings/{first['id']}", headers=other).status_code == 403
    assert client.patch(f"/api/bookings/{second['id']}/cancel", headers=other).status_code == 403
    prop_row = db.get(Property, prop["id"])
    prop_row.status = ListingStatus.inactive
    db.commit()
    history = client.get("/api/bookings/mine", headers=renter).json()
    assert {b["status"] for b in history} == {"confirmed", "cancelled"}
    assert all(b["property"]["title"] == prop["title"] for b in history)
    assert all(b["property"]["status"] == "inactive" for b in history)
    assert all("documents" not in b["property"] and "owner_email" not in b["property"] for b in history)
    assert client.get(f"/api/properties/{prop['id']}", headers=renter).status_code == 404
    detail = client.get(f"/api/bookings/{second['id']}", headers=renter)
    assert detail.status_code == 200
    assert detail.json()["property"]["address"] == prop["address"]


def test_renter_cancels_confirmed_stay_and_keeps_history(client, db, make_property, owner, renter):
    prop = make_property()
    request = _booking(prop["id"])
    b = client.post("/api/bookings/", headers=renter, json=request).json()
    client.patch(f"/api/bookings/{b['id']}/accept", headers=owner)
    result = client.patch(f"/api/bookings/{b['id']}/cancel", headers=renter)
    assert result.status_code == 200
    assert result.json()["cancellation_reason"] == "renter_cancelled"
    assert result.json()["cancelled_at"]
    assert client.patch(f"/api/bookings/{b['id']}/cancel", headers=renter).status_code == 400
    assert client.patch(f"/api/bookings/{b['id']}/accept", headers=owner).status_code == 409
    owner_rows = client.get("/api/bookings/owner", headers=owner).json()
    assert owner_rows[0]["cancellation_reason"] == "renter_cancelled"
    assert client.get(f"/api/bookings/property/{prop['id']}/availability").json() == []
    assert client.post("/api/bookings/", headers=renter, json=request).status_code == 201


def test_rejection_and_owner_or_admin_cancellation_are_distinct(client, make_property, owner, renter, admin):
    prop = make_property()
    for offset, endpoint, headers, reason in [
        (10, "decline", owner, "owner_declined"),
        (90, "cancel", owner, "owner_cancelled"),
        (180, "cancel", admin, "admin_cancelled"),
    ]:
        b = client.post("/api/bookings/", headers=renter, json=_booking(prop["id"], start_days=offset)).json()
        result = client.patch(f"/api/bookings/{b['id']}/{endpoint}", headers=headers)
        assert result.status_code == 200, result.text
        assert result.json()["cancellation_reason"] == reason
        history = client.get(f"/api/bookings/{b['id']}", headers=renter).json()
        assert history["cancelled_at"] and history["cancellation_reason"] == reason


def test_completed_stay_cannot_be_cancelled(client, db, make_property, owner, renter):
    prop = make_property()
    b = client.post("/api/bookings/", headers=renter, json=_booking(prop["id"], start_days=-100, nights=1)).json()
    stored = db.get(Booking, b["id"])
    stored.status = BookingStatus.confirmed
    db.commit()
    for headers in (renter, owner):
        result = client.patch(f"/api/bookings/{b['id']}/cancel", headers=headers)
        assert result.status_code == 409
    history = client.get("/api/bookings/mine", headers=renter).json()
    assert history[0]["status"] == "confirmed"
    assert history[0]["cancellation_reason"] is None
    assert history[0]["cancelled_at"] is None
