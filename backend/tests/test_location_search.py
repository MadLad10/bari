import httpx
import pytest

from models import Property
from services import location


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "places_provider", "overpass")
    location._cache.clear()
    location._cooldown = 0
    location._last_request = 0
    yield
    location._cache.clear()
    location._cooldown = 0


def test_filtered_pagination_count_and_all_page_map(client, make_property):
    ids = [make_property(price=1000 + i, rental_type="daily", latitude=23.75 + i / 10000,
                         longitude=90.4, safety_score=4.5, university_distance_km=1.2)["id"] for i in range(23)]
    make_property(rental_type="monthly", latitude=23.8, longitude=90.4)
    params = {"rental_type": "daily", "min_safety_score": 4, "max_university_distance_km": 1.5}
    assert client.get("/api/properties/count", params=params).json()["count"] == 23
    first = client.get("/api/properties/", params={**params, "limit": 20}).json()
    second = client.get("/api/properties/", params={**params, "skip": 20, "limit": 20}).json()
    assert len(first) == 20 and len(second) == 3
    assert {p["id"] for p in first + second} == set(ids)
    assert not {p["id"] for p in first} & {p["id"] for p in second}
    mapped = client.get("/api/properties/map", params={**params, "skip": 20, "limit": 1}).json()
    assert mapped["total"] == 23 and len(mapped["items"]) == 23
    assert all("owner_phone" not in point for point in mapped["items"])
    assert client.get("/api/properties/", params={**params, "min_safety_score": 4.6}).json() == []
    assert client.get("/api/properties/", params={**params, "max_university_distance_km": 1}).json() == []


def test_map_honors_publication_and_reports_missing_coordinates(client, db, make_property):
    public = make_property(latitude=23.75, longitude=90.4)
    make_property()  # genuinely unknown location; never pin to an invented area centroid
    held = make_property(latitude=23.8, longitude=90.4, is_female_only=True)
    row = db.get(Property, held["id"])
    row.women_safety_status = "not_submitted"
    db.commit()
    mapped = client.get("/api/properties/map").json()
    assert mapped["total"] == 2 and mapped["missing_coordinates"] == 1
    assert [p["id"] for p in mapped["items"]] == [public["id"]]


def test_search_rejects_invalid_safety_and_distance(client):
    for params in ({"min_safety_score": 5.1}, {"min_safety_score": -1}, {"max_university_distance_km": -1}):
        for path in ("/api/properties/", "/api/properties/count", "/api/properties/map"):
            assert client.get(path, params=params).status_code == 422


def test_coordinate_edits_require_pairs_and_withdraw_approval(client, make_property, owner):
    prop = make_property(is_female_only=True, latitude=23.75, longitude=90.4)
    for payload in ({"latitude": 24}, {"latitude": 91, "longitude": 90}, {"latitude": None, "longitude": 90}):
        assert client.put(f"/api/properties/{prop['id']}", headers=owner, json=payload).status_code == 422
    changed = client.put(f"/api/properties/{prop['id']}", headers=owner,
                         json={"latitude": 23.76, "longitude": 90.41}).json()
    assert changed["status"] == "pending" and changed["women_safety_status"] == "not_submitted"
    assert changed["document_check_status"] == "not_submitted"


def fake_places():
    return {"elements": [
        {"type": "node", "id": 11, "lat": 23.7505, "lon": 90.4, "tags": {"amenity": "hospital", "name": "Test Hospital"}},
        {"type": "node", "id": 12, "lat": 23.7502, "lon": 90.4, "tags": {"highway": "bus_stop", "name": "Test Bus Stop"}},
        {"type": "way", "id": 13, "center": {"lat": 23.751, "lon": 90.4}, "tags": {"shop": "supermarket", "name": "Test Market"}},
        {"type": "node", "id": 14, "lat": 24.75, "lon": 90.4, "tags": {"amenity": "hospital", "name": "Too far away"}},
    ]}


def test_nearby_actual_place_geometry_distance_and_route(client, make_property, monkeypatch):
    prop = make_property(latitude=23.75, longitude=90.4)
    calls = []
    def provider(key, ttl, method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == "POST":
            return fake_places()
        return {"code": "Ok", "routes": [{"distance": 123.4, "duration": 43,
                    "geometry": {"type": "LineString", "coordinates": [[90.4, 23.75], [90.4, 23.7505]]}}]}
    monkeypatch.setattr(location, "_request_json", provider)
    nearby = client.get(f"/api/properties/{prop['id']}/nearby").json()
    hospital = nearby["categories"]["hospital"][0]
    assert hospital["name"] == "Test Hospital" and hospital["distance_m"] == 56
    assert len(nearby["categories"]["hospital"]) == 1
    assert nearby["categories"]["market"][0]["id"] == "way/13"
    result = client.post(f"/api/properties/{prop['id']}/route", json={"destination_id": hospital["id"]}).json()
    assert result["distance_m"] == 123 and result["duration_s"] == 43
    assert result["mode"] == "driving" and result["traffic_included"] is False
    assert result["geometry"]["type"] == "LineString"
    assert "/route/v1/driving/90.4,23.75;90.4,23.7505" in calls[-1][1]
    assert client.post(f"/api/properties/{prop['id']}/route", json={"destination_id": "node/999"}).status_code == 400


def test_hidden_or_unlocated_properties_never_call_external_provider(client, make_property, owner, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Unexpected network lookup")
    monkeypatch.setattr(location, "_request_json", unexpected)
    prop = make_property()
    assert client.get(f"/api/properties/{prop['id']}/nearby").status_code == 400
    client.put(f"/api/properties/{prop['id']}", headers=owner, json={"status": "inactive"})
    assert client.get(f"/api/properties/{prop['id']}/nearby").status_code == 404
    assert client.post(f"/api/properties/{prop['id']}/route", json={"destination_id": "node/11"}).status_code == 404


def test_network_cache_and_failure_cooldown(monkeypatch):
    calls = []
    real_client = httpx.Client
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"elements": []})
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    for _ in range(2):
        assert location._request_json("cache-test", 60, "GET", "https://example.test") == {"elements": []}
    assert len(calls) == 1
    location._cache.clear()
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(lambda request: httpx.Response(429)), **kwargs))
    with pytest.raises(location.LocationUnavailable):
        location._request_json("fail", 60, "GET", "https://example.test")
    assert location._cooldown > 0
    with pytest.raises(location.LocationUnavailable):
        location._request_json("different-key", 60, "GET", "https://example.test")


def test_no_route_does_not_invent_road_distance(client, make_property, monkeypatch):
    prop = make_property(latitude=23.75, longitude=90.4)
    monkeypatch.setattr(location, "_request_json", lambda key, ttl, method, *args, **kwargs:
                        fake_places() if method == "POST" else {"code": "NoRoute", "routes": []})
    response = client.post(f"/api/properties/{prop['id']}/route", json={"destination_id": "node/11"})
    assert response.status_code == 503


def test_photon_categories_preserve_real_ids_and_ignore_wrong_categories(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "places_provider", "photon")
    requests = []
    def provider(key, ttl, method, url, **kwargs):
        requests.append(kwargs["params"])
        return {"features": [
            {"geometry": {"type": "Point", "coordinates": [90.4, 23.7505]},
             "properties": {"osm_type": "W", "osm_id": 55, "osm_key": "amenity", "osm_value": "hospital", "name": "Hospital evidence"}},
            {"geometry": {"type": "Point", "coordinates": [90.4, 23.751]},
             "properties": {"osm_type": "N", "osm_id": 56, "osm_key": "amenity", "osm_value": "cafe", "name": "Not a hospital"}},
        ]}
    monkeypatch.setattr(location, "_request_json", provider)
    prop = Property(id=1, latitude=23.75, longitude=90.4)
    result = location.nearby(prop)
    assert result["categories"]["hospital"][0]["id"] == "way/55"
    assert len(result["categories"]["hospital"]) == 1
    assert result["categories"]["market"] == []
    assert len(requests) == 3
    assert all(("bbox", next(v for k, v in params if k == "bbox")) in params for params in requests)
