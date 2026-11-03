"""The admin's statistics: the customers' journey, kept even once an album
is deleted, without the admin's own tests."""
import asyncio
from datetime import datetime, timezone

import pytest

from tests.test_api import _signup


@pytest.fixture()
def admin(client, db, monkeypatch):
    from app.core import auth

    email, headers = _signup(client, db=db)
    monkeypatch.setattr(auth, "ADMIN_EMAIL", email)
    return headers


def _album(client, db, headers):
    album_id = client.post("/api/albums", json={"title": "Byblos", "size": "A5", "target_pages": 24}, headers=headers).json()["id"]
    asyncio.run(db.albums.update_one({"id": album_id}, {"$set": {"pages": [{"id": "1", "items": []}], "status": "ready"}}))
    return album_id


def _user_id(client, headers):
    return client.get("/api/auth/me", headers=headers).json()["id"]


def _stats(client, admin):
    res = client.get("/api/admin/stats", params={"days": 30}, headers=admin)
    assert res.status_code == 200, res.text
    body = res.json()
    return {**body, "funnel": {f["step"]: f["count"] for f in body["funnel"]}}


def test_the_journey_and_the_period(client, db, admin):
    before = _stats(client, admin)

    # A: an album put in the cart, then deleted — the steps stay.
    _, a = _signup(client, db=db)
    album_a = _album(client, db, a)
    assert client.post("/api/cart/items", json={"album_id": album_a, "kind": "print", "quantity": 1}, headers=a).status_code == 200
    assert client.delete(f"/api/albums/{album_a}", headers=a).json() == {"deleted": 1}
    # B: an album, ordered (two books).
    _, b = _signup(client, db=db)
    album_b = _album(client, db, b)
    now = datetime.now(timezone.utc).isoformat()
    asyncio.run(db.orders.insert_one({"id": "stats-order-b", "album_id": album_b, "user_id": _user_id(client, b), "kind": "print",
                                      "quantity": 2, "status": "pending_payment", "total_price_cents": 9100, "promo_code": "HELLO",
                                      "created_at": now}))
    # C: an account only.
    _signup(client, db=db)
    # The admin's own test album: not counted.
    _album(client, db, admin)

    after = _stats(client, admin)
    added = {step: after["funnel"][step] - before["funnel"][step] for step in after["funnel"]}
    assert added == {"accounts": 3, "album": 2, "photos": 2, "cart": 2, "ordered": 1}
    period = {k: after["period"][k] - before["period"][k] for k in ("albums_started", "orders", "books", "revenue_cents", "with_promo")}
    assert period == {"albums_started": 2, "orders": 1, "books": 2, "revenue_cents": 9100, "with_promo": 1}
    this_week = after["weekly"][-1]
    assert this_week["orders"] >= 1 and this_week["accounts"] >= 3 and len(after["weekly"]) == 12


def test_only_the_admin_sees_them(client, db):
    _, someone = _signup(client, db=db)
    assert client.get("/api/admin/stats", headers=someone).status_code == 403
