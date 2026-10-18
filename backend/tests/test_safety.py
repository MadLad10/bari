def test_vote_updates_average(client, make_property, renter):
    prop = make_property(safety_score=None)
    assert client.post(f"/api/safety/{prop['id']}/vote", headers=renter, json={"rating": 5}).json()["avg_score"] == 5
    res = client.post(f"/api/safety/{prop['id']}/vote", headers=renter, json={"rating": 3, "comment": "Dark lane at night"})
    assert res.status_code == 201
    assert res.json()["avg_score"] == 4.0
    assert client.get(f"/api/properties/{prop['id']}").json()["safety_score"] == 4.0


def test_vote_validation_and_404(client, make_property, renter):
    prop = make_property()
    assert client.post(f"/api/safety/{prop['id']}/vote", headers=renter, json={"rating": 6}).status_code == 422
    assert client.post("/api/safety/9999/vote", headers=renter, json={"rating": 4}).status_code == 404


def test_get_safety_stats(client, make_property, renter):
    prop = make_property()
    client.post(f"/api/safety/{prop['id']}/vote", headers=renter, json={"rating": 4, "comment": "Guard at gate", "voter_name": "Mim"})
    client.post(f"/api/safety/{prop['id']}/vote", headers=renter, json={"rating": 2})
    stats = client.get(f"/api/safety/{prop['id']}").json()
    assert stats["vote_count"] == 2
    assert stats["avg_score"] == 3.0
    names = {v["voter_name"] for v in stats["votes"]}
    assert names == {"Mim", "Anonymous"}


def test_safety_stats_empty(client, make_property, renter):
    prop = make_property()
    stats = client.get(f"/api/safety/{prop['id']}").json()
    assert stats == {"property_id": prop["id"], "avg_score": None, "vote_count": 0, "votes": []}


def test_vote_count_is_total_not_page_size(client, make_property, renter):
    prop = make_property()
    for _ in range(25):
        client.post(f"/api/safety/{prop['id']}/vote", headers=renter, json={"rating": 4})
    stats = client.get(f"/api/safety/{prop['id']}").json()
    assert stats["vote_count"] == 25
    assert len(stats["votes"]) == 20
