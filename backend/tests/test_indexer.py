from models import Document, Job
from jobs.queue import enqueue, run_pending
from jobs import queue as job_queue
from rag.indexer import index_source


def _docs(db, kind=None):
    db.expire_all()
    q = db.query(Document)
    return q.filter_by(source_type=kind).all() if kind else q.all()


def test_create_listing_enqueues_index_job_atomically(client, db, make_property):
    prop = make_property()
    jobs = db.query(Job).all()
    assert [(j.kind, j.payload) for j in jobs] == [("index", {"source_type": "listing", "source_id": prop["id"]})]
    assert run_pending(db) == 1
    [doc] = _docs(db, "listing")
    assert doc.property_id == prop["id"] and doc.embedding is not None and len(doc.embedding) == 1024


def test_index_is_idempotent_and_tracks_changes(client, db, make_property, owner):
    prop = make_property()
    assert index_source(db, "listing", prop["id"]) == {"chunks": 1, "embedded": 1, "removed": 0}
    assert index_source(db, "listing", prop["id"])["embedded"] == 0          # unchanged: no re-embedding
    client.put(f"/api/properties/{prop['id']}", json={"description": "Completely new description text."}, headers=owner)
    run_pending(db)
    [doc] = _docs(db, "listing")
    assert "Completely new description" in doc.content
    client.put(f"/api/properties/{prop['id']}", json={"status": "inactive"}, headers=owner)
    run_pending(db)
    assert _docs(db, "listing") == []                                         # inactive: not searchable


def test_enqueue_dedupes_pending_jobs(db):
    for _ in range(3):
        enqueue(db, "index", {"source_type": "listing", "source_id": 1}, dedupe_key="index:listing:1")
        db.commit()
    assert db.query(Job).count() == 1


def test_forum_and_safety_writes_are_indexed(client, db, make_property, renter):
    prop = make_property()
    post = client.post("/api/forum/", headers=renter, json={
        "title": "Badda flooding", "body": "The lanes flood every monsoon.", "post_type": "neighborhood"}).json()
    client.post(f"/api/forum/{post['id']}/comments", headers=renter, json={"content": "Buy gumboots!"})
    client.post(f"/api/safety/{prop['id']}/vote", headers=renter, json={"rating": 2, "comment": "Dark at night"})
    client.post(f"/api/safety/{prop['id']}/vote", headers=renter, json={"rating": 5})   # no comment: no job
    run_pending(db)
    assert {d.source_type for d in _docs(db)} == {"listing", "post", "comment", "safety"}
    assert len(_docs(db, "safety")) == 1


def test_delete_listing_removes_its_documents(client, db, make_property, owner, renter):
    prop = make_property()
    client.post(f"/api/safety/{prop['id']}/vote", headers=renter, json={"rating": 2, "comment": "Dark at night"})
    run_pending(db)
    assert len(_docs(db)) == 2
    client.delete(f"/api/properties/{prop['id']}", headers=owner)
    assert _docs(db) == []


def test_failing_job_retries_then_fails(db, monkeypatch):
    calls = []

    def boom(db, payload):
        calls.append(1)
        raise RuntimeError("embedding server down")

    monkeypatch.setitem(job_queue.HANDLERS, "boom", boom)
    enqueue(db, "boom", {})
    db.commit()
    job = db.query(Job).one()
    job.max_attempts = 2
    db.commit()
    run_pending(db)
    db.expire_all()
    job = db.query(Job).one()
    assert job.status == "queued" and job.attempts == 1 and "embedding server down" in job.last_error
    db.execute(Job.__table__.update().values(run_after=Job.created_at))   # skip the backoff wait
    db.commit()
    run_pending(db)
    db.expire_all()
    assert db.query(Job).one().status == "failed" and len(calls) == 2


def test_concurrent_indexing_of_same_source_is_serialised(client, db, make_property):
    import threading
    from database import SessionLocal
    prop = make_property()
    errors = []

    def work():
        s = SessionLocal()
        try:
            index_source(s, "listing", prop["id"])
        except Exception as e:  # noqa: BLE001
            errors.append(e)
        finally:
            s.close()

    threads = [threading.Thread(target=work) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
    assert len(_docs(db, "listing")) == 1
