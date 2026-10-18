from datetime import datetime, timedelta, timezone

from tests.conftest import make_user, property_payload


def _signup(client, **kw):
    data = {"email": "mim@example.com", "password": "password123", "name": "Mim", "role": "renter"}
    data.update(kw)
    return client.post("/api/auth/signup", json=data)


def test_signup_login_me(client):
    res = _signup(client)
    assert res.status_code == 201
    token = res.json()["access_token"]
    assert res.json()["user"]["role"] == "renter"
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["email"] == "mim@example.com"

    login = client.post("/api/auth/login", json={"email": "MIM@example.com", "password": "password123"})
    assert login.status_code == 200
    assert client.post("/api/auth/login", json={"email": "mim@example.com", "password": "wrong-pass"}).status_code == 401


def test_signup_rules(client):
    assert _signup(client).status_code == 201
    assert _signup(client).status_code == 409                       # duplicate email
    assert _signup(client, email="a@example.com", role="admin").status_code == 400
    assert _signup(client, email="b@example.com", password="short").status_code == 422


def test_bad_tokens_rejected(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_only_owners_create_listings(client, renter, owner):
    assert client.post("/api/properties/", json=property_payload()).status_code == 401
    assert client.post("/api/properties/", json=property_payload(), headers=renter).status_code == 403
    res = client.post("/api/properties/", json=property_payload(), headers=owner)
    assert res.status_code == 201


def test_owner_can_only_edit_own_listing(client, db, make_property, admin):
    _, other_owner = make_user(db, "owner")
    prop = make_property()
    assert client.put(f"/api/properties/{prop['id']}", json={"price": 1}, headers=other_owner).status_code == 403
    assert client.delete(f"/api/properties/{prop['id']}", headers=other_owner).status_code == 403
    assert client.put(f"/api/properties/{prop['id']}", json={"price": 5000}, headers=admin).status_code == 200


def test_bookings_belong_to_renter(client, db, make_property, renter, owner):
    prop = make_property()
    start = datetime.now(timezone.utc) + timedelta(days=5)
    payload = {"property_id": prop["id"], "renter_name": "Rafi", "renter_phone": "01811000000",
               "check_in": start.isoformat(), "check_out": (start + timedelta(days=30)).isoformat(),
               "rental_type": "monthly"}
    assert client.post("/api/bookings/", json=payload).status_code == 401
    b = client.post("/api/bookings/", json=payload, headers=renter).json()
    assert [x["id"] for x in client.get("/api/bookings/mine", headers=renter).json()] == [b["id"]]

    _, stranger = make_user(db, "renter")
    assert client.get(f"/api/bookings/{b['id']}", headers=stranger).status_code == 403
    assert client.patch(f"/api/bookings/{b['id']}/cancel", headers=stranger).status_code == 403
    assert client.get(f"/api/bookings/{b['id']}", headers=owner).status_code == 200   # listing owner
    # renter contact details in the per-property list are owner-only
    assert client.get(f"/api/bookings/property/{prop['id']}", headers=stranger).status_code == 403


def test_forum_author_comes_from_account(client, renter):
    res = client.post("/api/forum/", headers=renter, json={
        "title": "Is Badda safe?", "body": "Asking for a friend moving there.", "post_type": "neighborhood",
        "author_name": "Someone Else"})
    assert res.json()["author_name"] == "Rafi Renter"
    assert client.post("/api/forum/", json={"title": "Anon post", "body": "Should not be allowed",
                                           "post_type": "neighborhood"}).status_code == 401
