import os
import sys
from pathlib import Path

import pytest

# Point the app at the dedicated test database before any app module is imported.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://bari:bari@localhost:5433/bari_test"
)
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["LLM_PROVIDER"] = "fake"
os.environ["EMBEDDING_PROVIDER"] = "fake"
os.environ["RERANKER"] = "fake"
os.environ["JWT_SECRET"] = "test-secret-that-is-at-least-32-bytes-long"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from database import Base, SessionLocal, engine  # noqa: E402
from main import app  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def _migrated_schema():
    """Build the schema through the real Alembic migrations, so tests also cover them."""
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")
    yield


def _truncate():
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def _clean_tables(request):
    # Read-only tests marked `shared_seed` reuse one seeded + indexed database per module.
    if request.node.get_closest_marker("shared_seed") is None:
        _truncate()
    yield


@pytest.fixture(scope="module")
def _seeded_module(_migrated_schema):
    """Full synthetic fixture set, indexed with the fake embedder, once per module."""
    from rag.indexer import all_sources, index_source
    from seed import seed
    _truncate()
    session = SessionLocal()
    seed(session)
    for kind, sid in all_sources(session):
        index_source(session, kind, sid)
    yield session
    session.close()
    _truncate()


@pytest.fixture
def seeded(request, _seeded_module, db):
    """Seeded + indexed DB. Tests using it must be marked `shared_seed` and must not write."""
    assert request.node.get_closest_marker("shared_seed"), "mark tests using `seeded` with @pytest.mark.shared_seed"
    from models import Property
    assert db.query(Property).count() == 150, (
        "shared seed was wiped: keep `shared_seed` tests in modules without non-shared DB tests")
    return db


@pytest.fixture
def needles():
    import json
    from seed import DATA
    return json.loads((DATA / "needles.json").read_text())


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def property_payload(**overrides):
    data = {
        "title": "Furnished 2-bed flat near BRAC University",
        "description": "Bright 2-bedroom apartment 8 minutes walk from BRAC University main gate.",
        "property_type": "apartment",
        "listing_type": "sublet",
        "rental_type": "monthly",
        "furnishing": "furnished",
        "price": 12000,
        "bedrooms": 2,
        "bathrooms": 1,
        "address": "Road 4, Block B, Niketan, Gulshan",
        "area": "Gulshan",
        "nearby_university": "BRAC University",
        "university_distance_km": 0.8,
        "is_female_only": False,
        "safety_score": 4.5,
        "amenities": ["AC", "WiFi"],
        "owner_name": "Karim Hossain",
        "owner_phone": "01711000001",
        "owner_email": "karim@example.com",
    }
    data.update(overrides)
    return data


def make_user(db, role="renter", email=None, name="Test User"):
    from models import UserRole
    from services.users import create_token, create_user
    email = email or f"{role}{make_user.counter}@example.com"
    make_user.counter += 1
    user = create_user(db, email=email, password="password123", name=name, role=UserRole(role))
    return user, {"Authorization": f"Bearer {create_token(user)}"}


make_user.counter = 0


@pytest.fixture
def owner(db):
    return make_user(db, "owner", name="Karim Owner")[1]


@pytest.fixture
def renter(db):
    return make_user(db, "renter", name="Rafi Renter")[1]


@pytest.fixture
def admin(db):
    return make_user(db, "admin", name="Admin")[1]


@pytest.fixture
def make_property(client, owner):
    def _make(headers=None, **overrides):
        res = client.post("/api/properties/", json=property_payload(**overrides), headers=headers or owner)
        assert res.status_code == 201, res.text
        return res.json()
    return _make
