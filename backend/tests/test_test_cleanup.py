"""The one-time cleanup of the pre-launch test accounts and orders (admin)."""
import asyncio

from tests.test_admin_address import admin  # noqa: F401  (fixture)
from tests.test_api import _signup


def _me(client, headers):
    return client.get("/api/auth/me", headers=headers).json()


def test_a_test_account_goes_with_everything_in_it(client, db, admin, monkeypatch):  # noqa: F811
    from app.services import accounts

    folders = []
    monkeypatch.setattr(accounts, "delete_prefix", lambda prefix: folders.append(prefix) or 0)
    email, headers = _signup(client, db=db)
    user_id = _me(client, headers)["id"]
    album_id = client.post("/api/albums", json={"title": "Test"}, headers=headers).json()["id"]
    asyncio.run(db.orders.insert_one({"id": "t-order-1", "user_id": user_id, "album_id": album_id, "kind": "print", "status": "printing"}))
    asyncio.run(db.carts.insert_one({"user_id": user_id, "items": []}))
    listed = {a["email"]: a for a in client.get("/api/admin/test-cleanup/accounts", headers=admin).json()}
    assert listed[email]["albums"] == 1 and listed[email]["orders"] == 1
    # The email must be typed again.
    assert client.post(f"/api/admin/test-cleanup/accounts/{user_id}/delete", json={"confirm": "nope"}, headers=admin).status_code == 400
    res = client.post(f"/api/admin/test-cleanup/accounts/{user_id}/delete", json={"confirm": email.upper()}, headers=admin)
    assert res.status_code == 200 and res.json()["orders"] == 1
    assert folders and folders[0].endswith(f"/users/{user_id}/")  # the photos in storage too
    assert not asyncio.run(db.users.find_one({"id": user_id}))
    assert not asyncio.run(db.albums.find_one({"id": album_id}))
    assert not asyncio.run(db.orders.find_one({"id": "t-order-1"}))
    assert not asyncio.run(db.carts.find_one({"user_id": user_id}))


def test_the_admin_account_and_customers_are_safe(client, db, admin):  # noqa: F811
    me = _me(client, admin)
    assert client.post(f"/api/admin/test-cleanup/accounts/{me['id']}/delete", json={"confirm": me["email"]}, headers=admin).status_code == 400
    _, headers = _signup(client, db=db)
    assert client.get("/api/admin/test-cleanup/accounts", headers=headers).status_code == 403


def test_only_a_cancelled_order_is_deleted_with_its_album(client, db, admin):  # noqa: F811
    me = _me(client, admin)
    album_id = client.post("/api/albums", json={"title": "Mine"}, headers=admin).json()["id"]
    order = {"id": "abcd1234-test", "user_id": me["id"], "album_id": album_id, "kind": "print", "status": "printing"}
    asyncio.run(db.orders.insert_one(order))
    url = "/api/admin/test-cleanup/orders/abcd1234-test/delete"
    assert client.post(url, json={"confirm": "EB-ABCD1234"}, headers=admin).status_code == 400  # not cancelled
    asyncio.run(db.orders.update_one({"id": "abcd1234-test"}, {"$set": {"status": "cancelled"}}))
    assert "EB-ABCD1234" in [o["number"] for o in client.get("/api/admin/test-cleanup/orders", headers=admin).json()]
    assert client.post(url, json={"confirm": "eb-abcd1234"}, headers=admin).status_code == 200
    assert not asyncio.run(db.orders.find_one({"id": "abcd1234-test"}))
    assert not asyncio.run(db.albums.find_one({"id": album_id}))
