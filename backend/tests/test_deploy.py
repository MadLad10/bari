"""Production/serverless pieces: Gemini embeddings, keyword fallback, rate limit, inline jobs, platform defaults."""
import json

import httpx
import pytest

import config
from config import Settings, apply_platform_defaults, normalize_database_url
from llm.base import LLMError
from models import AgentRun, Document
from tests.conftest import make_user


# ── settings ──────────────────────────────────────────────────────────────────

def test_hosted_postgres_urls_get_the_psycopg_driver():
    assert normalize_database_url("postgres://u:p@h/db?sslmode=require") == "postgresql+psycopg://u:p@h/db?sslmode=require"
    assert normalize_database_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_database_url("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"


def test_vercel_defaults_apply_only_on_vercel_and_yield_to_explicit_env():
    s = apply_platform_defaults(Settings(), environ={"VERCEL": "1", "RERANKER": "bge"})
    assert (s.db_serverless, s.jobs_mode, s.upload_dir) == (True, "inline", "/tmp/uploads")
    local = apply_platform_defaults(Settings(), environ={})
    assert (local.db_serverless, local.jobs_mode) == (False, "worker")


# ── Gemini embeddings ─────────────────────────────────────────────────────────

@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setattr(config.settings, "gemini_api_key", "test-key")
    from rag.embeddings import GeminiEmbedder
    calls = []

    def make(responses):
        def handler(req):
            calls.append(json.loads(req.content) | {"_key": req.headers.get("x-goog-api-key")})
            status, body = responses.pop(0)
            return httpx.Response(status, json=body)
        return GeminiEmbedder(transport=httpx.MockTransport(handler), sleep=lambda s: None)
    return make, calls


def test_gemini_query_and_document_task_types(gemini):
    make, calls = gemini
    emb = make([(200, {"embeddings": [{"values": [0.1] * 1024}]}),
                (200, {"embeddings": [{"values": [0.2] * 1024}, {"values": [0.3] * 1024}]})])
    assert len(emb.embed_query("নিরাপদ রুম")) == 1024
    assert len(emb.embed(["doc one", "doc two"])) == 2
    assert calls[0]["requests"][0]["taskType"] == "RETRIEVAL_QUERY"
    assert calls[1]["requests"][0]["taskType"] == "RETRIEVAL_DOCUMENT"
    assert calls[0]["requests"][0]["outputDimensionality"] == 1024 and calls[0]["_key"] == "test-key"
    assert emb.model == "gemini-embedding-001@1024"


def test_gemini_retries_rate_limits_but_not_bad_requests(gemini):
    make, calls = gemini
    emb = make([(429, {}), (503, {}), (200, {"embeddings": [{"values": [0.0] * 1024}]})])
    assert len(emb.embed_query("x")) == 1024 and len(calls) == 3
    bad = make([(400, {"error": "bad"})])
    with pytest.raises(LLMError, match="400"):
        bad.embed_query("x")


def test_search_falls_back_to_keywords_when_embeddings_fail(client, db, make_property):
    from jobs.queue import run_pending
    from rag.embeddings import set_embedder_override
    from rag.hybrid import hybrid_search
    prop = make_property(title="Rooftop garden flat in Aftabnagar")
    run_pending(db)

    class Down:
        model, dim = "down", 1024

        def embed_query(self, text):
            raise LLMError("gemini HTTP 429", retryable=True)

    set_embedder_override(Down())
    try:
        res = hybrid_search(db, "rooftop garden", sources=["listing"], k=5)
    finally:
        set_embedder_override(None)
    assert res.stages["vector_unavailable"] is True and res.stages["keyword"] is True
    assert [h.source_id for h in res.hits] == [prop["id"]]


# ── assistant rate limit ──────────────────────────────────────────────────────

def test_assistant_rate_limit_per_client(client, db, monkeypatch):
    from llm.client import LLMClient, set_llm_override
    from llm.fake import FakeProvider
    from llm.base import LLMResponse
    monkeypatch.setattr(config.settings, "ai_rate_limit_per_hour", 2)
    set_llm_override(LLMClient(FakeProvider([LLMResponse("hi")] * 5), sleep=lambda s: None))
    _, headers = make_user(db, "renter")
    body = {"messages": [{"role": "user", "content": "hello"}], "stream": False}
    try:
        assert client.post("/api/ai/chat", json=body, headers=headers).status_code == 200
        assert client.post("/api/ai/chat", json=body, headers=headers).status_code == 200
        limited = client.post("/api/ai/chat", json=body, headers=headers)
        assert limited.status_code == 429 and "limit" in limited.json()["message"]
        assert client.post("/api/ai/chat", json=body).status_code == 200   # a different client (anonymous IP)
    finally:
        set_llm_override(None)
    keys = {r.client_key for r in db.query(AgentRun).all()}
    assert any(k.startswith("user:") for k in keys) and any(k.startswith("ip:") for k in keys)


# ── inline jobs (no worker on Vercel) ─────────────────────────────────────────

def test_inline_jobs_mode_indexes_and_moderates_within_the_request(client, db, renter, monkeypatch):
    monkeypatch.setattr(config.settings, "jobs_mode", "inline")
    post = client.post("/api/forum/", headers=renter, json={
        "title": "Call me for rooms", "body": "Cheap rooms, call 01712345678 now", "post_type": "roommate"}).json()
    db.expire_all()
    from models import ForumPost
    assert db.get(ForumPost, post["id"]).moderation_status == "held"   # moderated before the response returned
    ok = client.post("/api/forum/", headers=renter, json={
        "title": "Badda rent question", "body": "How much is a room in Badda now?", "post_type": "neighborhood"}).json()
    db.expire_all()
    assert db.query(Document).filter_by(source_type="post", source_id=ok["id"]).count() == 1


def test_admin_password_can_differ_from_the_public_demo_password(db, client, monkeypatch):
    import seed
    monkeypatch.setattr(config.settings, "admin_password", "a-real-secret-123")
    seed.seed(db)
    login = lambda pw: client.post("/api/auth/login", json={"email": "admin@example.com", "password": pw}).status_code
    assert login(seed.DEMO_PASSWORD) == 401 and login("a-real-secret-123") == 200
    assert client.post("/api/auth/login", json={"email": "student@example.com",
                                                "password": seed.DEMO_PASSWORD}).status_code == 200
