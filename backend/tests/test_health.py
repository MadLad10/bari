def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok", "database": "ok"}


def test_health_explains_a_missing_database_on_vercel(client, monkeypatch):
    import config
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(config.settings, "database_url", "sqlite:///./bari.db")
    res = client.get("/api/health")
    assert res.status_code == 503 and res.json()["database"] == "DATABASE_URL is not set"
