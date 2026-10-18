from tests.conftest import property_payload


def test_create_and_get_property(client, make_property):
    prop = make_property()
    assert prop["id"] > 0
    assert prop["status"] == "active"
    res = client.get(f"/api/properties/{prop['id']}")
    assert res.status_code == 200
    assert res.json()["title"] == prop["title"]


def test_create_property_validation(client, owner):
    res = client.post("/api/properties/", json=property_payload(title="abc"), headers=owner)
    assert res.status_code == 422
    res = client.post("/api/properties/", json=property_payload(price=0), headers=owner)
    assert res.status_code == 422


def test_get_missing_property_404(client):
    assert client.get("/api/properties/9999").status_code == 404


def test_list_filters(client, make_property):
    cheap = make_property(price=7000, is_female_only=True, area="Dhanmondi",
                          nearby_university="North South University", bedrooms=1)
    pricey = make_property(price=30000, bedrooms=3, safety_score=3.0)

    ids = lambda r: {p["id"] for p in r.json()}
    assert ids(client.get("/api/properties/", params={"max_price": 10000})) == {cheap["id"]}
    assert ids(client.get("/api/properties/", params={"min_price": 10000})) == {pricey["id"]}
    assert ids(client.get("/api/properties/", params={"is_female_only": True})) == {cheap["id"]}
    assert ids(client.get("/api/properties/", params={"bedrooms": 3})) == {pricey["id"]}
    assert ids(client.get("/api/properties/", params={"area": "dhanmondi"})) == {cheap["id"]}
    assert ids(client.get("/api/properties/", params={"nearby_university": "North South"})) == {cheap["id"]}
    assert ids(client.get("/api/properties/", params={"min_safety_score": 4})) == {cheap["id"]}
    assert ids(client.get("/api/properties/", params={"q": "Dhanmondi"})) == {cheap["id"]}


def test_list_hides_inactive_and_paginates(client, make_property, owner):
    a = make_property()
    make_property()
    client.put(f"/api/properties/{a['id']}", json={"status": "inactive"}, headers=owner)
    assert len(client.get("/api/properties/").json()) == 1
    assert len(client.get("/api/properties/", params={"limit": 1, "skip": 5}).json()) == 0


def test_count(client, make_property):
    make_property(price=5000)
    make_property(price=50000)
    assert client.get("/api/properties/count").json() == {"count": 2}
    assert client.get("/api/properties/count", params={"max_price": 6000}).json() == {"count": 1}


def test_update_property(client, make_property, owner):
    prop = make_property()
    res = client.put(f"/api/properties/{prop['id']}", json={"price": 9999, "is_female_only": True}, headers=owner)
    assert res.status_code == 200
    assert res.json()["price"] == 9999
    assert res.json()["is_female_only"] is True
    assert client.put("/api/properties/9999", json={"price": 1}, headers=owner).status_code == 404


def test_delete_property(client, make_property, owner):
    prop = make_property()
    assert client.delete(f"/api/properties/{prop['id']}", headers=owner).status_code == 204
    assert client.get(f"/api/properties/{prop['id']}").status_code == 404
    assert client.delete(f"/api/properties/{prop['id']}", headers=owner).status_code == 404


def test_upload_photo_and_document(client, make_property, owner, tmp_path, monkeypatch):
    import routers.properties as props_router
    monkeypatch.setattr(props_router, "UPLOAD_DIR", str(tmp_path))
    prop = make_property()

    res = client.post(f"/api/properties/{prop['id']}/photos",
                      files={"file": ("a.png", b"\x89PNG fake", "image/png")}, headers=owner)
    assert res.status_code == 200
    assert res.json()["url"].endswith(".png")
    assert len(client.get(f"/api/properties/{prop['id']}").json()["photos"]) == 1

    bad = client.post(f"/api/properties/{prop['id']}/photos",
                      files={"file": ("a.txt", b"hi", "text/plain")}, headers=owner)
    assert bad.status_code == 400

    doc = client.post(f"/api/properties/{prop['id']}/documents",
                      files={"file": ("deed.pdf", b"%PDF", "application/pdf")}, headers=owner)
    assert doc.status_code == 200
    assert doc.json()["name"] == "deed.pdf"
