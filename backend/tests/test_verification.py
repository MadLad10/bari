import io
from pathlib import Path

import pytest

from config import settings
from models import Property, PropertyDocument
from services import verification
from tests.conftest import make_user, property_payload

TEXT = "TENANCY AGREEMENT\nOwner: Karim Owner\nProperty: House 12, Green Road, Dhanmondi\nThe landlord provides this apartment for residential tenancy."


def document_pdf(text=TEXT):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    stream = DecodedStreamObject()
    lines = ["BT /F1 14 Tf 30 750 Td 20 TL"]
    for line in text.splitlines():
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        lines.append(f"({escaped}) Tj T*")
    stream.set_data(("\n".join(lines) + "\nET").encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    import routers.properties
    monkeypatch.setattr(settings, "private_upload_dir", str(tmp_path / "private"))
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "photos"))
    monkeypatch.setattr(routers.properties, "UPLOAD_DIR", settings.upload_dir)
    Path(settings.upload_dir).mkdir()


def draft(client, headers, **overrides):
    data = property_payload(owner_name="Karim Owner", address="House 12, Green Road, Dhanmondi", area="Dhanmondi")
    result = client.post("/api/properties/", headers=headers, json={**data, **overrides})
    assert result.status_code == 201, result.text
    return result.json()


def upload(client, prop, owner, text=TEXT):
    r = client.post(f"/api/properties/{prop['id']}/documents", headers=owner,
                    files={"file": ("deed.pdf", document_pdf(text), "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()


def test_new_listing_waits_for_checks_and_cannot_be_self_published(client, owner):
    prop = draft(client, owner)
    assert prop["status"] == "pending"
    assert client.get(f"/api/properties/{prop['id']}").status_code == 404
    assert client.get("/api/properties/").json() == []
    assert client.get(f"/api/properties/{prop['id']}", headers=owner).status_code == 200
    assert client.put(f"/api/properties/{prop['id']}", headers=owner, json={"status": "active"}).status_code == 403


def test_matching_pdf_auto_publishes_and_documents_stay_private(client, db, owner, renter, admin):
    prop = draft(client, owner)
    doc = upload(client, prop, owner)
    assert verification.verify_documents(db, prop["id"])["status"] == "passed"
    result = client.get(f"/api/properties/{prop['id']}").json()
    assert result["status"] == "active" and result["document_check_status"] == "passed"
    assert "documents" not in result
    _, unrelated = make_user(db, "owner")
    for headers, code in [({}, 401), (renter, 403), (unrelated, 403), (owner, 200), (admin, 200)]:
        download = client.get(doc["url"], headers=headers)
        assert download.status_code == code
        if code == 200:
            assert download.content.startswith(b"%PDF-")
            assert download.headers["cache-control"] == "no-store"
    row = db.get(PropertyDocument, doc["id"])
    assert client.get(f"/uploads/{row.stored_name}").status_code == 404
    assert client.get(f"/api/properties/{prop['id']}/verification", headers=unrelated).status_code == 403


def test_mismatch_goes_to_admin_and_rejection_cannot_be_bypassed(client, db, owner, admin):
    prop = draft(client, owner)
    upload(client, prop, owner, TEXT.replace("Karim Owner", "Unrelated Person"))
    assert verification.verify_documents(db, prop["id"])["status"] == "needs_review"
    queue = client.get("/api/admin/queue", headers=admin).json()["listings"]
    assert queue[0]["verification"]["documents"] and "account holder" in queue[0]["reason"]
    assert client.post(f"/api/admin/listings/{prop['id']}/reject", headers=admin).status_code == 200
    client.put(f"/api/properties/{prop['id']}", headers=owner, json={"status": "inactive"})
    assert client.put(f"/api/properties/{prop['id']}", headers=owner, json={"status": "active"}).status_code == 403
    assert client.get(f"/api/properties/{prop['id']}").status_code == 404


def test_admin_can_review_uncertain_document_but_cannot_approve_without_one(client, db, owner, admin):
    prop = draft(client, owner)
    assert client.post(f"/api/admin/listings/{prop['id']}/approve", headers=admin).status_code == 400
    upload(client, prop, owner, TEXT.replace("12", "999"))
    verification.verify_documents(db, prop["id"])
    r = client.post(f"/api/admin/listings/{prop['id']}/approve", headers=admin)
    assert r.status_code == 200
    assert client.get(f"/api/properties/{prop['id']}").json()["document_check_status"] == "reviewed"


def test_same_document_across_accounts_requires_review(client, db, owner):
    first = draft(client, owner)
    upload(client, first, owner)
    verification.verify_documents(db, first["id"])
    _, second_owner = make_user(db, "owner", name="Karim Owner")
    second = draft(client, second_owner)
    upload(client, second, second_owner)
    assert verification.verify_documents(db, second["id"])["status"] == "needs_review"
    reasons = client.get(f"/api/properties/{second['id']}/verification", headers=second_owner).json()["reasons"]
    assert any("another owner" in r for r in reasons)


def test_address_edits_and_document_removal_withdraw_publication(client, db, owner):
    prop = draft(client, owner)
    doc = upload(client, prop, owner)
    verification.verify_documents(db, prop["id"])
    assert client.put(f"/api/properties/{prop['id']}", headers=owner, json={"address": "House 99, Other Road, Dhanmondi"}).status_code == 200
    assert client.get(f"/api/properties/{prop['id']}").status_code == 404
    assert verification.verify_documents(db, prop["id"])["status"] == "needs_review"
    assert client.delete(doc["url"], headers=owner).status_code == 204
    assert client.get(doc["url"], headers=owner).status_code == 404


def test_legacy_document_urls_are_blocked_even_when_added_as_photos(client, db, make_property, owner, admin):
    prop = make_property()
    path = Path(settings.upload_dir) / "legacy-proof.pdf"
    path.write_bytes(document_pdf())
    row = db.get(Property, prop["id"])
    row.documents = ["/uploads/legacy-proof.pdf"]
    row.photos = ["/uploads/legacy-proof.pdf"]
    db.commit()
    assert client.get("/uploads/legacy-proof.pdf").status_code == 404
    protected = f"/api/properties/{prop['id']}/documents/legacy/legacy-proof.pdf"
    assert client.get(protected).status_code == 401
    assert client.get(protected, headers=owner).status_code == 200
    assert client.get(protected, headers=admin).status_code == 200
    assert "documents" not in client.get(f"/api/properties/{prop['id']}").json()


def test_invalid_uploads_and_document_url_injection_are_rejected(client, owner):
    prop = draft(client, owner)
    base = f"/api/properties/{prop['id']}"
    for content, mime in [(b"%PDF", "application/pdf"), (b"hello", "text/plain"), (b"X" * (verification.MAX_BYTES + 1), "image/png")]:
        r = client.post(base + "/documents", headers=owner, files={"file": ("fake.pdf", content, mime)})
        assert r.status_code == 400
    assert client.put(base, headers=owner, json={"documents": ["/uploads/other.pdf"]}).status_code == 422
    assert client.put(base, headers=owner, json={"documents": None}).status_code == 422


def test_local_ocr_reads_scanned_document(client, db, owner):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (1800, 600), "white")
    ImageDraw.Draw(image).multiline_text((40, 40), TEXT, fill="black", font=ImageFont.load_default(size=30), spacing=20)
    data = io.BytesIO()
    image.save(data, format="PNG")
    prop = draft(client, owner)
    response = client.post(f"/api/properties/{prop['id']}/documents", headers=owner,
                           files={"file": ("scan.png", data.getvalue(), "image/png")})
    assert response.status_code == 200
    assert verification.verify_documents(db, prop["id"])["status"] == "passed"
