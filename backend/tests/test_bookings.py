from datetime import datetime, timedelta, timezone


def _booking(prop_id, start_days=10, nights=60, **kw):
    start = datetime.now(timezone.utc) + timedelta(days=start_days)
    data = {
        "property_id": prop_id,
        "renter_name": "Rafi",
        "renter_phone": "01811000000",
        "check_in": start.isoformat(),
        "check_out": (start + timedelta(days=nights)).isoformat(),
        "rental_type": "monthly",
    }
    data.update(kw)
    return data


def test_create_booking_computes_monthly_price(client, make_property, renter):
    prop = make_property(price=10000)
    res = client.post("/api/bookings/", headers=renter, json=_booking(prop["id"], nights=60))
    assert res.status_code == 201, res.text
    assert res.json()["total_price"] == 20000
    assert res.json()["status"] == "pending"


def test_daily_and_hourly_price(client, make_property, renter):
    prop = make_property(price=500, rental_type="daily")
    res = client.post("/api/bookings/", headers=renter, json=_booking(prop["id"], nights=3, rental_type="daily"))
    assert res.json()["total_price"] == 1500
    prop = make_property(price=500, rental_type="hourly")
    start = datetime.now(timezone.utc) + timedelta(days=200)
    res = client.post("/api/bookings/", headers=renter, json={
        **_booking(prop["id"]), "rental_type": "hourly",
        "check_in": start.isoformat(), "check_out": (start + timedelta(hours=4)).isoformat()})
    assert res.json()["total_price"] == 2000


def test_booking_validation(client, make_property, renter):
    prop = make_property()
    assert client.post("/api/bookings/", headers=renter, json=_booking(prop["id"], nights=0)).status_code == 400
    assert client.post("/api/bookings/", headers=renter, json=_booking(9999)).status_code == 404


def test_booking_overlap_conflict(client, make_property, renter):
    prop = make_property()
    assert client.post("/api/bookings/", headers=renter, json=_booking(prop["id"])).status_code == 201
    assert client.post("/api/bookings/", headers=renter, json=_booking(prop["id"], start_days=20)).status_code == 409
    assert client.post("/api/bookings/", headers=renter, json=_booking(prop["id"], start_days=100)).status_code == 201


def test_availability_and_listing(client, make_property, renter, owner):
    prop = make_property()
    b = client.post("/api/bookings/", headers=renter, json=_booking(prop["id"])).json()
    avail = client.get(f"/api/bookings/property/{prop['id']}/availability").json()
    assert len(avail) == 1
    listed = client.get(f"/api/bookings/property/{prop['id']}", headers=owner).json()
    assert [x["id"] for x in listed] == [b["id"]]
    assert client.get(f"/api/bookings/{b['id']}", headers=renter).status_code == 200
    assert client.get("/api/bookings/9999", headers=renter).status_code == 404


def test_cancel_booking_frees_dates(client, make_property, renter):
    prop = make_property()
    b = client.post("/api/bookings/", headers=renter, json=_booking(prop["id"])).json()
    res = client.patch(f"/api/bookings/{b['id']}/cancel", headers=renter)
    assert res.status_code == 200 and res.json()["status"] == "cancelled"
    assert client.patch(f"/api/bookings/{b['id']}/cancel", headers=renter).status_code == 400
    assert client.get(f"/api/bookings/property/{prop['id']}/availability").json() == []
    assert client.post("/api/bookings/", headers=renter, json=_booking(prop["id"])).status_code == 201


def test_quote_and_booking_agree_on_started_days_and_months(client, make_property, renter):
    start = datetime.now(timezone.utc) + timedelta(days=100)
    for period, duration, expected in [("daily", timedelta(hours=36), 2000),
                                       ("monthly", timedelta(days=30, minutes=1), 2000),
                                       ("hourly", timedelta(minutes=90), 1500)]:
        prop = make_property(price=1000, rental_type=period)
        interval = {"property_id": prop["id"], "check_in": start.isoformat(),
                    "check_out": (start + duration).isoformat(), "rental_type": period}
        quote = client.post("/api/bookings/quote", json=interval)
        assert quote.status_code == 200, quote.text
        booking = client.post("/api/bookings/", headers=renter,
                              json={**_booking(prop["id"]), **interval})
        assert quote.json()["total_price"] == booking.json()["total_price"] == expected
        assert booking.json()["status"] == "pending"


def test_quote_rejects_invalid_or_unavailable_dates(client, make_property, renter):
    prop = make_property()
    body = _booking(prop["id"])
    assert client.post("/api/bookings/", headers=renter, json=body).status_code == 201
    interval = {k: body[k] for k in ("property_id", "check_in", "check_out", "rental_type")}
    assert client.post("/api/bookings/quote", json=interval).status_code == 409
    interval["check_out"] = interval["check_in"]
    assert client.post("/api/bookings/quote", json=interval).status_code == 400
