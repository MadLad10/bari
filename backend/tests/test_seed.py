import json

from models import ForumPost, Property, SafetyVote
from seed import DATA, seed


def test_seed_loads_fixtures_with_stable_ids(db, client, renter):
    counts = seed(db)
    assert counts["properties"] == 150
    assert counts["posts"] == 200
    assert counts["safety_votes"] > 500
    needles = json.loads((DATA / "needles.json").read_text())

    brac = db.get(Property, needles["listings"]["brac_2bed_women_safe"])
    assert brac.is_female_only and brac.nearby_university == "BRAC University"
    assert db.get(ForumPost, needles["posts"]["merul_badda_flooding"]).area == "Merul Badda"
    assert db.get(SafetyVote, needles["safety_votes"]["brac_female_guard"]).property_id == brac.id

    # sequences continue after the fixture IDs, so new rows don't collide
    res = client.post("/api/forum/", headers=renter, json={"title": "New post here", "body": "A brand new forum post",
                                           "post_type": "experience", "author_name": "Test"})
    assert res.json()["id"] == 201


def test_seed_is_idempotent(db):
    seed(db)
    assert seed(db) == {}
    assert db.query(Property).count() == 150


def test_seeded_bangla_content_searchable(db, client):
    seed(db)
    res = client.get("/api/properties/", params={"q": "ধানমন্ডি", "limit": 100})
    assert res.status_code == 200
    assert any("ধানমন্ডি" in p["title"] for p in res.json())


def test_seed_creates_demo_accounts(db, client):
    from seed import DEMO_PASSWORD
    seed(db)
    res = client.post("/api/auth/login", json={"email": "owner@example.com", "password": DEMO_PASSWORD})
    assert res.status_code == 200
    token = res.json()["access_token"]
    upd = client.put("/api/properties/1", json={"price": 12500}, headers={"Authorization": f"Bearer {token}"})
    assert upd.status_code == 200
    assert client.put("/api/properties/20", json={"price": 1},
                      headers={"Authorization": f"Bearer {token}"}).status_code == 403
