"""The admin's test PDF of an album in the one-sheet hardcover format: for
the admin only, made without any order, nothing sent to the printer."""
import asyncio

import pytest

from tests.test_api import _signup


@pytest.fixture()
def setup(client, db, monkeypatch):
    from app.core import auth
    from app.routers import admin as admin_router
    from app.services import test_pdf

    email, admin = _signup(client, db=db)
    monkeypatch.setattr(auth, "ADMIN_EMAIL", email)
    _, customer = _signup(client, db=db)
    album_id = client.post("/api/albums", json={"title": "Santorini", "size": "A5", "target_pages": 24}, headers=admin).json()["id"]
    asyncio.run(db.albums.update_one({"id": album_id}, {"$set": {"pages": [{"id": "1", "items": []}, {"id": "2", "items": []}]}}))
    rendered, stored = [], {}
    monkeypatch.setattr(test_pdf, "render_album_pdf_sync", lambda url, n, label="": rendered.append((url, n)) or b"%PDF-test")
    monkeypatch.setattr(test_pdf, "put_object", lambda path, data, ctype=None: stored.__setitem__(path, data))

    class R2:
        def generate_presigned_url(self, op, Params, ExpiresIn):
            return f"https://r2.example/{Params['Key']}"

    monkeypatch.setattr(admin_router, "get_r2_client", lambda: R2())
    return {"admin": admin, "customer": customer, "album_id": album_id, "rendered": rendered, "stored": stored, "token": admin["Authorization"].split()[1]}


def test_the_admin_gets_a_test_pdf_without_any_order(client, db, setup):
    album_id, admin = setup["album_id"], setup["admin"]
    assert client.get(f"/api/admin/albums/{album_id}/test-pdf", headers=admin).json() == {"status": "none"}
    state = client.post(f"/api/admin/albums/{album_id}/test-pdf", headers=admin).json()
    assert state["status"] == "ready" and state["pages"] == 2 and "path" not in state
    url, pages = setup["rendered"][0]
    assert "format=hardcover" in url and pages == 2
    from app.services.test_pdf import test_pdf_path

    assert setup["stored"] == {test_pdf_path(album_id): b"%PDF-test"}
    # No order, so nothing for the printer.
    assert asyncio.run(db.orders.count_documents({"album_id": album_id})) == 0
    res = client.get(f"/api/admin/albums/{album_id}/test-pdf/download", params={"auth": setup["token"]}, follow_redirects=False)
    assert res.status_code in (302, 307) and res.headers["location"].endswith(f"test-pdfs/{album_id}.pdf")


def test_no_one_else_can_ask_for_it_or_download_it(client, db, setup):
    album_id, customer = setup["album_id"], setup["customer"]
    assert client.post(f"/api/admin/albums/{album_id}/test-pdf", headers=customer).status_code == 403
    assert client.get(f"/api/admin/albums/{album_id}/test-pdf", headers=customer).status_code == 403
    token = customer["Authorization"].split()[1]
    assert client.get(f"/api/admin/albums/{album_id}/test-pdf/download", params={"auth": token}, follow_redirects=False).status_code == 403
    assert client.get(f"/api/admin/albums/{album_id}/test-pdf/download", follow_redirects=False).status_code == 401
    assert setup["rendered"] == []
