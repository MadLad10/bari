def _msg(prop_id, **kw):
    data = {"property_id": prop_id, "session_token": "tok123", "sender": "renter",
            "sender_name": "Rafi", "content": "Is it still available?"}
    data.update(kw)
    return data


def test_post_and_get_messages(client, make_property):
    prop = make_property()
    assert client.post("/api/chat/", json=_msg(prop["id"])).status_code == 201
    client.post("/api/chat/", json=_msg(prop["id"], sender="owner", sender_name="Karim", content="Yes"))
    client.post("/api/chat/", json=_msg(prop["id"], session_token="other"))
    msgs = client.get(f"/api/chat/{prop['id']}/tok123").json()
    assert [m["sender"] for m in msgs] == ["renter", "owner"]
    assert client.post("/api/chat/", json=_msg(9999)).status_code == 404


def test_websocket_broadcast(client, make_property):
    prop = make_property()
    with client.websocket_connect(f"/api/chat/ws/{prop['id']}/tok123") as a, \
         client.websocket_connect(f"/api/chat/ws/{prop['id']}/tok123") as b:
        a.send_json({"sender": "renter", "sender_name": "Rafi", "content": "hello"})
        assert a.receive_json()["content"] == "hello"
        assert b.receive_json()["content"] == "hello"
    assert len(client.get(f"/api/chat/{prop['id']}/tok123").json()) == 1
