"""The admin can open and fix a customer's ordered album before it's
printed; the customer stays locked out of editing it, and nobody else can
see it."""
import asyncio
import uuid

import pytest

from tests.test_api import _signup


@pytest.fixture()
def people(client, db, monkeypatch):
    from app.core import auth

    admin_email, admin_headers = _signup(client, db=db)
    monkeypatch.setattr(auth, "ADMIN_EMAIL", admin_email)
    _, customer = _signup(client, db=db)
    _, stranger = _signup(client, db=db)
    album_id = client.post("/api/albums", json={"title": "Wedding"}, headers=customer).json()["id"]
    owner_id = asyncio.run(db.albums.find_one({"id": album_id}))["user_id"]
    asyncio.run(db.orders.insert_one({"id": str(uuid.uuid4()), "album_id": album_id, "user_id": owner_id, "status": "paid"}))
    return {"admin": admin_headers, "customer": customer, "stranger": stranger, "album_id": album_id, "owner_id": owner_id}


def test_the_admin_can_open_and_edit_a_customers_ordered_album(client, people):
    url = f"/api/albums/{people['album_id']}"
    album = client.get(url, headers=people["admin"]).json()
    assert album["admin_editing"] is True and album["was_ordered"] is False

    res = client.patch(url, json={"title": "Wedding (fixed)", "base_version": album["version"]}, headers=people["admin"])
    assert res.status_code == 200 and res.json()["title"] == "Wedding (fixed)"
    assert client.get(f"{url}/status", headers=people["admin"]).status_code == 200


def test_the_customer_stays_locked_out_of_her_ordered_album(client, people):
    url = f"/api/albums/{people['album_id']}"
    album = client.get(url, headers=people["customer"]).json()
    assert album["was_ordered"] is True and album["admin_editing"] is False
    assert client.patch(url, json={"title": "Changed"}, headers=people["customer"]).status_code == 403


def test_another_customer_still_cannot_see_it(client, people):
    url = f"/api/albums/{people['album_id']}"
    assert client.get(url, headers=people["stranger"]).status_code == 404
    assert client.patch(url, json={"title": "Hacked"}, headers=people["stranger"]).status_code == 404


def test_an_image_the_admin_adds_to_the_cover_is_kept_with_the_customers_files(client, people, monkeypatch):
    from app.routers import covers

    stored = {}
    monkeypatch.setattr(covers, "store_image_with_thumbnail", lambda path, data, ctype: (stored.setdefault("path", {"path": path}), None, 10, 10))
    res = client.post(
        f"/api/albums/{people['album_id']}/cover-assets",
        files={"file": ("logo.png", b"\x89PNG fake", "image/png")},
        headers=people["admin"],
    )
    assert res.status_code == 200
    assert f"/users/{people['owner_id']}/albums/{people['album_id']}/" in res.json()["storage_path"]


def test_cover_images_of_a_customer_open_for_the_admin_only(client, people, monkeypatch):
    from app.routers import covers

    monkeypatch.setattr(covers, "get_object", lambda path: (b"img", "image/png"))
    path = f"everbook/users/{people['owner_id']}/albums/{people['album_id']}/cover-assets/a.png"
    get = lambda who: client.get("/api/cover-assets/image", params={"path": path, "variant": "original"}, headers=people[who])
    assert get("admin").status_code == 200
    assert get("customer").status_code == 200
    assert get("stranger").status_code == 403
