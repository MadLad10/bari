from datetime import datetime, timedelta, timezone

from models import Booking, BookingStatus
from tests.conftest import make_user
from tests.test_bookings import _booking


def test_owner_booking_decisions_and_history(client, db, make_property, owner, renter):
    prop = make_property()
    b = client.post("/api/bookings/", headers=renter, json=_booking(prop["id"])).json()
    _, other_owner = make_user(db, "owner")
    for headers in (renter, other_owner):
        assert client.patch(f"/api/bookings/{b['id']}/accept", headers=headers).status_code == 403
        assert client.patch(f"/api/bookings/{b['id']}/decline", headers=headers).status_code == 403
    assert client.get("/api/bookings/owner").status_code == 401
    assert client.get("/api/bookings/owner", headers=renter).status_code == 403
    assert client.get("/api/bookings/owner", headers=other_owner).json() == []
    assert client.patch(f"/api/bookings/{b['id']}/accept", headers=owner).json()["status"] == "confirmed"
    assert client.get(f"/api/bookings/{b['id']}", headers=renter).json()["status"] == "confirmed"
    assert client.patch(f"/api/bookings/{b['id']}/accept", headers=owner).status_code == 409
    assert client.patch(f"/api/bookings/{b['id']}/decline", headers=owner).status_code == 409
    assert client.delete(f"/api/properties/{prop['id']}", headers=owner).status_code == 409
    client.patch(f"/api/bookings/{b['id']}/cancel", headers=owner)
    new = client.post("/api/bookings/", headers=renter, json=_booking(prop["id"])).json()
    assert client.patch(f"/api/bookings/{new['id']}/decline", headers=owner).json()["status"] == "cancelled"
    assert len(client.get("/api/bookings/owner", headers=owner).json()) == 2
    assert client.get(f"/api/bookings/property/{prop['id']}/availability").json() == []


def test_accept_rechecks_visibility_and_legacy_overlaps(client, db, make_property, owner, renter):
    prop = make_property()
    b = client.post("/api/bookings/", headers=renter, json=_booking(prop["id"])).json()
    client.put(f"/api/properties/{prop['id']}", headers=owner, json={"status": "inactive"})
    assert client.patch(f"/api/bookings/{b['id']}/accept", headers=owner).status_code == 409
    client.put(f"/api/properties/{prop['id']}", headers=owner, json={"status": "active"})
    original = db.get(Booking, b["id"])
    overlap = Booking(property_id=prop["id"], renter_name="Legacy renter", renter_phone="01811000000",
                      check_in=original.check_in, check_out=original.check_out, rental_type=original.rental_type,
                      total_price=12000, status=BookingStatus.confirmed)
    db.add(overlap); db.commit()
    assert client.patch(f"/api/bookings/{b['id']}/accept", headers=owner).status_code == 409
    assert client.patch(f"/api/bookings/{b['id']}/decline", headers=owner).status_code == 200


def test_past_request_cannot_be_accepted(client, make_property, owner, renter):
    prop = make_property()
    b = client.post("/api/bookings/", headers=renter, json=_booking(prop["id"], start_days=-100, nights=1)).json()
    assert client.patch(f"/api/bookings/{b['id']}/accept", headers=owner).status_code == 409
    assert client.patch(f"/api/bookings/{b['id']}/decline", headers=owner).status_code == 200


def test_listing_edit_all_pdf_fields_and_preserve_verification(client, make_property, owner):
    prop = make_property()
    changes = {"property_type": "room", "listing_type": "rent", "price": 1500, "rental_type": "daily",
               "furnishing": "semi_furnished", "has_furniture_for_sale": True, "bedrooms": 1, "bathrooms": 2,
               "nearby_university": "BRAC University", "university_distance_km": 0.5,
               "owner_email": "owner@example.com", "owner_phone": "01811000009", "is_female_only": True,
               "owner_name": prop["owner_name"], "address": prop["address"], "area": prop["area"]}
    result = client.put(f"/api/properties/{prop['id']}", headers=owner, json=changes)
    assert result.status_code == 200, result.text
    for key, value in changes.items():
        assert result.json()[key] == value
    assert result.json()["document_check_status"] == "reviewed"
    assert result.json()["status"] == "pending"
    assert result.json()["women_safety_status"] == "not_submitted"
    sale = client.put(f"/api/properties/{prop['id']}", headers=owner,
                      json={"listing_type": "sale", "rental_type": "daily"}).json()
    assert sale["rental_type"] is None
    moved = client.put(f"/api/properties/{prop['id']}", headers=owner, json={"city": "Chattogram"}).json()
    assert moved["status"] == "pending"


def test_invalid_edits_rejected(client, make_property, owner):
    prop = make_property()
    for body in ({"price": 0}, {"price": -1}, {"title": ""}, {"price": None}, {"photos": None},
                 {"bedrooms": -1}, {"furnishing": None}, {"description": "short"}):
        assert client.put(f"/api/properties/{prop['id']}", headers=owner, json=body).status_code == 422
    assert client.put(f"/api/properties/{prop['id']}", headers=owner,
                      json={"photos": ["/uploads/doc_fake.pdf"]}).status_code == 400
