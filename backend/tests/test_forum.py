def _post(**kw):
    data = {"title": "Is Mohakhali safe at night?", "body": "Moving near BRAC soon, how are the lanes?",
            "post_type": "neighborhood", "area": "Mohakhali", "nearby_university": "BRAC University",
            "author_name": "Tania"}
    data.update(kw)
    return data


def test_create_get_and_list_posts(client, renter):
    p = client.post("/api/forum/", headers=renter, json=_post()).json()
    client.post("/api/forum/", headers=renter, json=_post(title="Looking for a roommate", post_type="roommate", area="Bashundhara"))
    assert client.get(f"/api/forum/{p['id']}").json()["title"] == p["title"]
    assert len(client.get("/api/forum/").json()) == 2
    assert len(client.get("/api/forum/", params={"post_type": "roommate"}).json()) == 1
    assert len(client.get("/api/forum/", params={"area": "mohakhali"}).json()) == 1
    assert len(client.get("/api/forum/", params={"q": "roommate"}).json()) == 1
    assert client.get("/api/forum/9999").status_code == 404


def test_post_validation(client, renter):
    assert client.post("/api/forum/", headers=renter, json=_post(title="hi")).status_code == 422
    assert client.post("/api/forum/", headers=renter, json=_post(post_type="spam")).status_code == 422


def test_upvote(client, renter):
    p = client.post("/api/forum/", headers=renter, json=_post()).json()
    client.post(f"/api/forum/{p['id']}/upvote", headers=renter)
    assert client.post(f"/api/forum/{p['id']}/upvote", headers=renter).json() == {"upvotes": 2}
    assert client.post("/api/forum/9999/upvote", headers=renter).status_code == 404


def test_comments(client, renter):
    p = client.post("/api/forum/", headers=renter, json=_post()).json()
    res = client.post(f"/api/forum/{p['id']}/comments", headers=renter, json={"author_name": "Arif", "content": "Safe till 11pm"})
    assert res.status_code == 201
    assert [c["content"] for c in client.get(f"/api/forum/{p['id']}/comments").json()] == ["Safe till 11pm"]
    assert client.get(f"/api/forum/{p['id']}").json()["comment_count"] == 1
    assert client.post("/api/forum/9999/comments", headers=renter, json={"author_name": "Arif", "content": "x y"}).status_code == 404
