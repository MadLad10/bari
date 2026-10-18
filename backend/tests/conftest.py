import os
import sys
import tempfile
from pathlib import Path

import pytest

# Point the app at a throwaway SQLite file before any app module is imported.
_TMP = tempfile.mkdtemp(prefix="bari-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ.setdefault("OPENAI_API_KEY", "")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from database import Base, engine  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


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


@pytest.fixture
def make_property(client):
    def _make(**overrides):
        res = client.post("/api/properties/", json=property_payload(**overrides))
        assert res.status_code == 201, res.text
        return res.json()
    return _make
