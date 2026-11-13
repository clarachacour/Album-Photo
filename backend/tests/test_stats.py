"""The admin's dashboard: the customers' journey, kept even once an album
is deleted, the albums' choices, the orders, without the admin's own tests."""
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


def _album(client, db, headers, template="travel-beirut", pages=24):
    body = {"title": "Byblos", "size": "A5", "target_pages": pages, "cover_template_id": template}
    album_id = client.post("/api/albums", json=body, headers=headers).json()["id"]
    asyncio.run(db.albums.update_one({"id": album_id}, {"$set": {"pages": [{"id": "1", "items": []}], "status": "ready"}}))
    return album_id


def _user_id(client, headers):
    return client.get("/api/auth/me", headers=headers).json()["id"]


def _dashboard(client, admin):
    res = client.get("/api/admin/dashboard", params={"days": 30}, headers=admin)
    assert res.status_code == 200, res.text
    return res.json()


def _counts(rows):
    return {r["key"]: r["count"] for r in rows}


def _added(after: dict, before: dict) -> dict:
    return {k: after.get(k, 0) - before.get(k, 0) for k in set(after) | set(before) if after.get(k, 0) != before.get(k, 0)}


def test_the_dashboard_follows_the_customers(client, db, admin):
    before = _dashboard(client, admin)

    # A: an album put in the cart, then deleted — the steps stay.
    _, a = _signup(client, db=db)
    album_a = _album(client, db, a, "travel-dubai", 50)
    assert client.post("/api/cart/items", json={"album_id": album_a, "kind": "print", "quantity": 1}, headers=a).status_code == 200
    assert client.delete(f"/api/albums/{album_a}", headers=a).json() == {"deleted": 1}
    # B: an album with 3 photos, ordered (two books), its PDF not made yet.
    _, b = _signup(client, db=db)
    album_b = _album(client, db, b)
    user_b = _user_id(client, b)
    asyncio.run(db.photos.insert_many([{"id": f"dash-ph-{i}", "album_id": album_b, "user_id": user_b, "is_deleted": False} for i in range(3)]))
    now = datetime.now(timezone.utc).isoformat()
    asyncio.run(db.orders.insert_one({"id": "dash-order-b", "album_id": album_b, "user_id": user_b, "kind": "print", "size": "A5",
                                      "quantity": 2, "page_count": 24, "status": "pending_payment", "total_price_cents": 9100, "shipping_price_cents": 500, "promo_code": "HELLO",
                                      "promo_discount_cents": 800, "pdf_ready": False, "created_at": now,
                                      "shipping_address": {"city": "Beirut", "area": "Hamra"}}))
    # C: a gift card bought (paid), another waiting for payment, and a
    # message through the contact form.
    _, c = _signup(client, db=db)
    user_c = _user_id(client, c)
    asyncio.run(db.gift_cards.insert_many([
        {"id": "dash-gift-1", "code": "DASH-GIFT-1", "buyer_user_id": user_c, "value_cents": 4800, "status": "active", "created_at": now, "expires_at": "2099-01-01T00:00:00+00:00"},
        {"id": "dash-gift-2", "code": "DASH-GIFT-2", "buyer_user_id": user_c, "value_cents": 4800, "status": "pending_payment", "created_at": now, "expires_at": "2099-01-01T00:00:00+00:00"},
    ]))
    assert client.post("/api/contact", json={"name": "C", "email": "c@example.com", "subject": "Hello", "message": "A question about sizes"}).status_code == 200
    # The admin's own test album: not counted.
    _album(client, db, admin, "travel-cairo")

    after = _dashboard(client, admin)
    funnel = lambda d: {f["step"]: f["count"] for f in d["funnel"]}  # noqa: E731
    assert _added(funnel(after), funnel(before)) == {"accounts": 3, "album": 2, "photos": 2, "cart": 2, "ordered": 1}
    kpis = {k: after["kpis"][k]["value"] - before["kpis"][k]["value"]
            for k in ("albums_started", "orders", "albums_ordered", "revenue_cents", "margin_cents", "messages")}
    # Two A5 24-page books: the printer's $24 + the $0.50 envelope each; the
    # $5 delivery goes to Wakilni.
    # What customers paid: the order and the gift card paid for.
    assert kpis == {"albums_started": 2, "orders": 1, "albums_ordered": 1, "revenue_cents": 9100 + 4800,
                    "margin_cents": 9100 + 4800 - 2 * 2450 - 500, "messages": 1}
    gifts = {k: after["gift_cards"][k] - before["gift_cards"][k] for k in ("sold", "sold_cents", "unused", "waiting_for_payment")}
    assert gifts == {"sold": 1, "sold_cents": 4800, "unused": 1, "waiting_for_payment": 1}
    assert after["money"]["printing_cents"] - before["money"]["printing_cents"] == 4900
    assert after["orders"]["printed"]["copies"] - before["orders"]["printed"]["copies"] == 2

    # Albums: created (the deleted one included) and ordered, by choice.
    rows = lambda d, g: {r["key"]: (r["created"], r["ordered"]) for r in d["albums"][g]}  # noqa: E731
    def added(group):
        a, b = rows(after, group), rows(before, group)
        return {k: (v[0] - b.get(k, (0, 0))[0], v[1] - b.get(k, (0, 0))[1]) for k, v in a.items() if v != b.get(k, (0, 0))}
    assert added("templates") == {"travel-dubai": (1, 0), "travel-beirut": (1, 1)}
    assert added("pages") == {"50": (1, 0), "24": (1, 1)}
    assert after["albums"]["photos_per_album"]["average"] is not None

    # Orders: the PDF still to make is listed, the promo code and the area.
    # Counted (the list shows the 20 oldest: other tests' orders can fill it).
    assert after["orders"]["pdf_not_ready"]["count"] - before["orders"]["pdf_not_ready"]["count"] == 1
    assert {p["code"]: p["discount_cents"] for p in after["orders"]["promo_codes"]}["HELLO"] >= 800
    assert _counts(after["orders"]["areas"])["Hamra"] >= 1
    assert len(after["weekly"]) == 5 and after["weekly"][-1]["orders"] >= 1
    assert len(after["monthly"]) == 12 and after["monthly"][-1]["albums_ordered"] - before["monthly"][-1]["albums_ordered"] == 1


def test_only_the_admin_sees_it(client, db):
    _, someone = _signup(client, db=db)
    assert client.get("/api/admin/dashboard", headers=someone).status_code == 403
