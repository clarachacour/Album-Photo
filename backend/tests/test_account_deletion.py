"""Deleting an account ("Delete my account" on the account page)."""
import asyncio

import pytest

from tests.test_api import _signup


@pytest.fixture()
def storage(monkeypatch):
    """Records what would be deleted from R2."""
    from app.services import accounts

    deleted = {"prefixes": [], "objects": []}
    monkeypatch.setattr(accounts, "delete_prefix", lambda prefix: deleted["prefixes"].append(prefix) or 3)
    monkeypatch.setattr(accounts, "delete_object", lambda path: path and deleted["objects"].append(path))
    monkeypatch.setattr("app.routers.auth.send_account_deleted_email", lambda *a, **k: None)
    return deleted


def _account_with_data(client, db, order_status="delivered"):
    email, headers = _signup(client, db=db)
    user = client.get("/api/auth/me", headers=headers).json()
    album_id = client.post("/api/albums", json={"title": "Trip"}, headers=headers).json()["id"]
    asyncio.run(db.photos.insert_one({"id": f"ph-{album_id}", "album_id": album_id, "user_id": user["id"], "storage_path": "x", "is_deleted": False}))
    if order_status:
        asyncio.run(db.orders.insert_one({"id": f"o-{album_id}", "album_id": album_id, "user_id": user["id"], "status": order_status, "pdf_path": f"albumai/orders/o-{album_id}.pdf", "shipping_address": {"full_name": "A"}}))
    return email, headers, user, album_id


def test_password_account_is_reported_as_having_one(client, db):
    _, headers = _signup(client, db=db)
    assert client.get("/api/auth/me", headers=headers).json()["has_password"] is True


def test_wrong_password_deletes_nothing(client, db, storage):
    _, headers, user, _ = _account_with_data(client, db)
    res = client.request("DELETE", "/api/auth/me", json={"password": "wrong"}, headers=headers)
    assert res.status_code == 401
    assert asyncio.run(db.users.find_one({"id": user["id"]}))
    assert storage["prefixes"] == []


def test_account_and_its_files_are_deleted_past_orders_kept(client, db, storage):
    email, headers, user, album_id = _account_with_data(client, db)
    res = client.request("DELETE", "/api/auth/me", json={"password": "secret123"}, headers=headers)
    assert res.status_code == 200, res.text
    assert asyncio.run(db.users.find_one({"id": user["id"]})) is None
    assert asyncio.run(db.albums.find_one({"user_id": user["id"]})) is None
    assert asyncio.run(db.photos.find_one({"user_id": user["id"]})) is None
    assert storage["prefixes"] == [f"albumai/users/{user['id']}/"]
    assert storage["objects"] == [f"albumai/orders/o-{album_id}.pdf"]
    order = asyncio.run(db.orders.find_one({"id": f"o-{album_id}"}))
    assert order["pdf_path"] is None and order["account_deleted_at"]  # sale record kept, no files
    # Gone for good: the old session and the password no longer work.
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.post("/api/auth/login", json={"email": email, "password": "secret123"}).status_code == 401


def test_order_in_progress_blocks_deletion(client, db, storage):
    _, headers, user, _ = _account_with_data(client, db, order_status="printing")
    res = client.request("DELETE", "/api/auth/me", json={"password": "secret123"}, headers=headers)
    assert res.status_code == 409
    assert asyncio.run(db.users.find_one({"id": user["id"]}))
    assert storage["prefixes"] == []


def test_google_account_deletes_without_password(client, db, storage):
    _, headers, user, _ = _account_with_data(client, db, order_status=None)
    asyncio.run(db.users.update_one({"id": user["id"]}, {"$set": {"password_hash": None}}))
    assert client.get("/api/auth/me", headers=headers).json()["has_password"] is False
    res = client.request("DELETE", "/api/auth/me", json={}, headers=headers)
    assert res.status_code == 200, res.text
    assert asyncio.run(db.users.find_one({"id": user["id"]})) is None


def test_prefix_delete_refuses_a_partial_folder_name():
    from app.services.storage import delete_prefix

    with pytest.raises(ValueError):
        delete_prefix("albumai/users/abc")
