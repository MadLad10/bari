import pytest
from contextlib import ExitStack
from starlette.websockets import WebSocketDisconnect

from tests.conftest import make_user


def _msg(prop_id, session, **kw):
    return {"property_id": prop_id, "session_token": session, "content": "Is it still available?", **kw}


def test_authenticated_chat_and_owner_inbox(client, db, make_property, owner):
    prop = make_property()
    user, renter = make_user(db, "renter", name="Rafi")
    token = f"user-{user.id}"
    assert client.post("/api/chat/", json=_msg(prop["id"], token)).status_code == 401
    posted = client.post("/api/chat/", headers=renter, json=_msg(prop["id"], token, sender="owner", sender_name="Fake"))
    assert posted.status_code == 201
    assert (posted.json()["sender"], posted.json()["sender_name"]) == ("renter", "Rafi")
    reply = client.post("/api/chat/", headers=owner, json=_msg(prop["id"], token, content="Yes, welcome"))
    assert reply.status_code == 201 and reply.json()["sender"] == "owner"
    msgs = client.get(f"/api/chat/{prop['id']}/{token}", headers=renter).json()
    assert [m["sender"] for m in msgs] == ["renter", "owner"]
    threads = client.get("/api/chat/inbox", headers=owner).json()
    assert threads[0]["renter_name"] == "Rafi"
    assert threads[0]["last_message"] == "Yes, welcome"
    assert threads[0]["property_title"] == prop["title"]
    assert client.get("/api/chat/inbox", headers=renter).status_code == 403
    assert client.post("/api/chat/", headers=renter, json=_msg(9999, token)).status_code == 404


def test_other_renters_and_owners_cannot_read_or_write_thread(client, db, make_property, owner):
    prop = make_property()
    user, renter = make_user(db, "renter")
    token = f"user-{user.id}"
    client.post("/api/chat/", headers=renter, json=_msg(prop["id"], token))
    _, stranger = make_user(db, "renter")
    _, other_owner = make_user(db, "owner")
    for headers in (stranger, other_owner):
        assert client.get(f"/api/chat/{prop['id']}/{token}", headers=headers).status_code == 403
        assert client.post("/api/chat/", headers=headers, json=_msg(prop["id"], token)).status_code == 403
    assert client.get(f"/api/chat/{prop['id']}/{token}").status_code == 401
    assert client.get("/api/chat/inbox", headers=other_owner).json() == []
    assert client.post("/api/chat/", headers=owner, json=_msg(prop["id"], "nonexistent")).status_code == 404


def test_websocket_authenticated_delivery_and_thread_isolation(client, db, make_property, owner):
    prop = make_property()
    user, renter = make_user(db, "renter")
    token = f"user-{user.id}"
    path = f"/api/chat/ws/{prop['id']}/{token}"
    with client.websocket_connect(path) as a, client.websocket_connect(path) as b:
        a.send_json({"token": renter["Authorization"].removeprefix("Bearer ")})
        b.send_json({"token": owner["Authorization"].removeprefix("Bearer ")})
        assert a.receive_json() == {"type": "ready"}
        assert b.receive_json() == {"type": "ready"}
        a.send_json({"content": "hello", "sender": "owner"})
        assert a.receive_json()["sender"] == "renter"
        assert b.receive_json()["content"] == "hello"
        # REST replies reach the renter's socket too.
        client.post("/api/chat/", headers=owner, json=_msg(prop["id"], token, content="Hello Rafi"))
        assert a.receive_json()["content"] == "Hello Rafi"
        assert b.receive_json()["content"] == "Hello Rafi"
    _, stranger = make_user(db, "renter")
    with client.websocket_connect(path) as socket:
        socket.send_json({"token": stranger["Authorization"].removeprefix("Bearer ")})
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()
    with client.websocket_connect(path) as socket:
        socket.send_json({"token": "invalid"})
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()


def test_chat_validation_and_paused_listing(client, db, make_property, owner):
    prop = make_property()
    user, renter = make_user(db, "renter")
    token = f"user-{user.id}"
    assert client.post("/api/chat/", headers=renter, json=_msg(prop["id"], token, content=" ")).status_code == 400
    assert client.post("/api/chat/", headers=renter, json=_msg(prop["id"], token, content="x" * 5001)).status_code == 422
    client.post("/api/chat/", headers=renter, json=_msg(prop["id"], token))
    client.put(f"/api/properties/{prop['id']}", headers=owner, json={"status": "inactive"})
    assert client.get(f"/api/chat/{prop['id']}/{token}", headers=renter).status_code == 200
    assert client.post("/api/chat/", headers=renter, json=_msg(prop["id"], token)).status_code == 201
    other, headers = make_user(db, "renter")
    assert client.post("/api/chat/", headers=headers, json=_msg(prop["id"], f"user-{other.id}")).status_code == 404


def _open_thread(stack, client, property_id, session, headers, initial):
    socket = stack.enter_context(client.websocket_connect(f"/api/chat/ws/{property_id}/{session}"))
    socket.send_json({"token": headers["Authorization"].removeprefix("Bearer ")})
    assert socket.receive_json() == {"type": "ready"}
    for content in initial:
        assert socket.receive_json()["content"] == content
    return socket


def test_two_renters_on_one_property_have_separate_live_conversations(client, db, make_property, owner):
    prop = make_property()
    one, first = make_user(db, "renter", name="First Renter")
    two, second = make_user(db, "renter", name="Second Renter")
    first_thread, second_thread = f"user-{one.id}", f"user-{two.id}"
    for headers, thread, content in [(first, first_thread, "first hello"), (second, second_thread, "second hello")]:
        assert client.post("/api/chat/", headers=headers, json=_msg(prop["id"], thread, content=content)).status_code == 201
    with ExitStack() as stack:
        renter_a = _open_thread(stack, client, prop["id"], first_thread, first, ["first hello"])
        owner_a = _open_thread(stack, client, prop["id"], first_thread, owner, ["first hello"])
        renter_b = _open_thread(stack, client, prop["id"], second_thread, second, ["second hello"])
        owner_b = _open_thread(stack, client, prop["id"], second_thread, owner, ["second hello"])
        # The authenticated URL fixes the thread and identity; client fields cannot redirect a message.
        renter_a.send_json({"content": "A private question", "session_token": second_thread,
                            "sender": "owner", "sender_name": "Forged Owner"})
        a = owner_a.receive_json()
        assert (a["content"], a["session_token"], a["sender"], a["sender_name"]) == (
            "A private question", first_thread, "renter", "First Renter")
        assert renter_a.receive_json()["content"] == "A private question"
        renter_b.send_json({"content": "B private question"})
        assert renter_b.receive_json()["content"] == "B private question"
        assert owner_b.receive_json()["content"] == "B private question"
        owner_a.send_json({"content": "A private reply"})
        assert owner_a.receive_json()["content"] == "A private reply"
        assert renter_a.receive_json()["content"] == "A private reply"
        client.post("/api/chat/", headers=owner, json=_msg(prop["id"], second_thread, content="B private reply"))
        assert renter_b.receive_json()["content"] == "B private reply"
        assert owner_b.receive_json()["content"] == "B private reply"
    first_rows = client.get(f"/api/chat/{prop['id']}/{first_thread}", headers=first).json()
    second_rows = client.get(f"/api/chat/{prop['id']}/{second_thread}", headers=second).json()
    assert [m["content"] for m in first_rows] == ["first hello", "A private question", "A private reply"]
    assert [m["content"] for m in second_rows] == ["second hello", "B private question", "B private reply"]
    threads = client.get("/api/chat/inbox", headers=owner).json()
    assert len(threads) == 2
    assert {c["session_token"]: c["last_message"] for c in threads} == {
        first_thread: "A private reply", second_thread: "B private reply"}


def test_same_renter_threads_are_separate_across_properties(client, db, make_property, owner):
    first_prop = make_property()
    second_prop = make_property(title="A different property with the same owner")
    user, renter = make_user(db, "renter")
    thread = f"user-{user.id}"
    with ExitStack() as stack:
        a = _open_thread(stack, client, first_prop["id"], thread, renter, [])
        b = _open_thread(stack, client, second_prop["id"], thread, renter, [])
        a.send_json({"content": "First property question", "property_id": second_prop["id"]})
        assert a.receive_json()["property_id"] == first_prop["id"]
        b.send_json({"content": "Second property question"})
        assert b.receive_json()["content"] == "Second property question"
        client.post("/api/chat/", headers=owner, json=_msg(first_prop["id"], thread, content="First property reply"))
        assert a.receive_json()["content"] == "First property reply"
    assert [m["content"] for m in client.get(f"/api/chat/{second_prop['id']}/{thread}", headers=renter).json()] == ["Second property question"]


def test_websocket_validation_does_not_break_the_conversation(client, db, make_property):
    prop = make_property()
    user, renter = make_user(db, "renter")
    thread = f"user-{user.id}"
    with ExitStack() as stack:
        socket = _open_thread(stack, client, prop["id"], thread, renter, [])
        socket.send_json({"content": " "})
        assert socket.receive_json() == {"error": "Enter a message"}
        socket.send_json({"content": "x" * 5001})
        assert "error" in socket.receive_json()
        socket.send_json({"content": "A valid question"})
        assert socket.receive_json()["content"] == "A valid question"
