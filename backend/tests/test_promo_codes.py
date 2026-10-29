"""Promo codes: made in the admin, a percentage off the albums (not the
delivery), once per customer, until a last day; the courier collects the
lower total."""
import asyncio
from datetime import date, timedelta

import pytest

from app.services.pricing import SHIPPING_PRICE_CENTS, compute_order_price_cents
from tests.test_admin_address import admin  # noqa: F401  (fixture)
from tests.test_cart import _checkout, shop  # noqa: F401  (fixture)
from tests.test_wakilni import courier  # noqa: F401  (fixture)

PRICE = compute_order_price_cents("A4", 24)


@pytest.fixture()
def welcome(client, db, admin):  # noqa: F811
    asyncio.run(db.promo_codes.delete_many({}))
    res = client.post("/api/admin/promo-codes", json={"code": " welcome10 ", "percent": 10}, headers=admin)
    assert res.status_code == 200, res.text
    return res.json()


def test_only_the_admin_makes_codes(client, shop, admin):  # noqa: F811
    assert client.post("/api/admin/promo-codes", json={"code": "HACK50", "percent": 50}, headers=shop["headers"]).status_code == 403
    assert client.post("/api/admin/promo-codes", json={"code": "OK", "percent": 10}, headers=admin).status_code == 422  # too short
    assert client.post("/api/admin/promo-codes", json={"code": "TOO MUCH!", "percent": 10}, headers=admin).status_code == 400
    assert client.post("/api/admin/promo-codes", json={"code": "HALF", "percent": 150}, headers=admin).status_code == 422


def test_a_code_takes_its_percent_off_the_albums_not_the_delivery(client, db, shop, admin, welcome):  # noqa: F811
    assert welcome["code"] == "WELCOME10" and welcome["uses"] == 0
    album = shop["album"]("Byblos")
    client.post("/api/cart/items", json={"album_id": album, "kind": "print", "quantity": 2}, headers=shop["headers"])
    cart = client.post("/api/cart/promo", json={"code": "welcome10"}, headers=shop["headers"]).json()
    discount = round(2 * PRICE * 0.10)
    assert cart["promo"] == {"code": "WELCOME10", "percent": 10, "problem": None}
    assert cart["discount_cents"] == discount
    assert cart["total_cents"] == cart["cash_cents"] == 2 * PRICE + SHIPPING_PRICE_CENTS - discount

    placed = _checkout(client, shop).json()
    order = placed["orders"][0]
    assert order["promo_code"] == "WELCOME10" and order["promo_discount_cents"] == discount
    assert order["total_price_cents"] == 2 * PRICE + SHIPPING_PRICE_CENTS - discount
    # Gone from the cart once used; counted in the admin.
    assert client.get("/api/cart", headers=shop["headers"]).json()["promo"] is None
    assert client.get("/api/admin/promo-codes", headers=admin).json()[0]["uses"] == 1


def test_once_per_customer(client, shop, welcome):
    album = shop["album"]("Tyre")
    client.post("/api/cart/items", json={"album_id": album, "kind": "print", "quantity": 1}, headers=shop["headers"])
    client.post("/api/cart/promo", json={"code": "WELCOME10"}, headers=shop["headers"])
    assert _checkout(client, shop).status_code == 200
    other = shop["album"]("Saida")
    client.post("/api/cart/items", json={"album_id": other, "kind": "print", "quantity": 1}, headers=shop["headers"])
    res = client.post("/api/cart/promo", json={"code": "WELCOME10"}, headers=shop["headers"])
    assert res.status_code == 400 and res.json()["detail"] == "promo_used"


def test_unknown_expired_and_switched_off_codes(client, shop, admin, welcome):  # noqa: F811
    bad = client.post("/api/cart/promo", json={"code": "NOPE"}, headers=shop["headers"])
    assert bad.json()["detail"] == "promo_unknown"
    yesterday = (date.today() - timedelta(days=2)).isoformat()
    client.post("/api/admin/promo-codes", json={"code": "SUMMER", "percent": 20, "ends_on": yesterday}, headers=admin)
    assert client.post("/api/cart/promo", json={"code": "summer"}, headers=shop["headers"]).json()["detail"] == "promo_expired"
    # Entered, then switched off before ordering: the cart says so, the checkout refuses it.
    album = shop["album"]("Jbeil")
    client.post("/api/cart/items", json={"album_id": album, "kind": "print", "quantity": 1}, headers=shop["headers"])
    client.post("/api/cart/promo", json={"code": "WELCOME10"}, headers=shop["headers"])
    assert client.patch("/api/admin/promo-codes/welcome10", json={"active": False}, headers=admin).json()["active"] is False
    cart = client.get("/api/cart", headers=shop["headers"]).json()
    assert cart["promo"]["problem"] == "inactive" and cart["discount_cents"] == 0
    assert _checkout(client, shop).status_code == 409
    client.delete("/api/cart/promo", headers=shop["headers"])
    assert _checkout(client, shop).status_code == 200


def test_the_courier_collects_the_lower_total(client, db, shop, welcome):
    from app.services import wakilni

    album = shop["album"]("Batroun")
    client.post("/api/cart/items", json={"album_id": album, "kind": "print", "quantity": 1}, headers=shop["headers"])
    client.post("/api/cart/promo", json={"code": "WELCOME10"}, headers=shop["headers"])
    order = _checkout(client, shop).json()["orders"][0]
    assert wakilni.cash_due(order) == PRICE + SHIPPING_PRICE_CENTS - round(PRICE * 0.10)
