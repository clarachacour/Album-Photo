"""The cart: albums added one by one (printed, PDF or both), then ordered
all at once — one order per album and version, delivery paid once, the
printed albums sent to the printer and the courier together."""
import asyncio

import pytest

from app.services.pricing import DIGITAL_PRICE_CENTS, SHIPPING_PRICE_CENTS, TERMS_VERSION, compute_order_price_cents
from tests.test_wakilni import ADDRESS, _order, _ready, courier  # noqa: F401  (fixture)


@pytest.fixture()
def shop(client, db, courier, monkeypatch):  # noqa: F811
    from app.routers import cart as cart_router

    emails = []
    monkeypatch.setattr(cart_router, "send_checkout_confirmation_email", lambda to, name, orders: emails.append([o["id"] for o in orders]))
    monkeypatch.setattr(cart_router, "send_order_confirmation_email", lambda to, name, order: emails.append([order["id"]]))
    headers = courier["customer"]
    # The fixture's own order isn't part of these tests' packages.
    asyncio.run(db.orders.update_one({"id": courier["order"]["id"]}, {"$unset": {"printer_pending_at": ""}}))

    def album(title, pages=24):
        album_id = client.post("/api/albums", json={"title": title, "size": "A4", "target_pages": 24}, headers=headers).json()["id"]
        asyncio.run(db.albums.update_one({"id": album_id}, {"$set": {"pages": [{"id": str(i), "items": []} for i in range(pages)], "status": "ready"}}))
        return album_id

    return {"headers": headers, "album": album, "emails": emails, "courier": courier}


def _add(client, shop, album_id, kind="print", quantity=1):
    return client.post("/api/cart/items", json={"album_id": album_id, "kind": kind, "quantity": quantity}, headers=shop["headers"])


def _checkout(client, shop, **extra):
    body = {"shipping_address": ADDRESS, "accepted_terms_version": TERMS_VERSION, **extra}
    return client.post("/api/cart/checkout", json=body, headers=shop["headers"])


def test_the_cart_prices_everything_with_one_delivery(client, shop, online_payment):
    a, b = shop["album"]("Byblos"), shop["album"]("Tyre", pages=60)
    assert _add(client, shop, a, quantity=2).status_code == 200
    _add(client, shop, b)
    cart = _add(client, shop, b, "digital").json()  # the same album as a PDF too: full price
    assert cart["count"] == 3
    prices = {(line["album_id"], line["kind"]): line["line_total_cents"] for line in cart["items"]}
    assert prices[(a, "print")] == 2 * compute_order_price_cents("A4", 24)
    assert prices[(b, "print")] == compute_order_price_cents("A4", 60)
    assert prices[(b, "digital")] == DIGITAL_PRICE_CENTS
    assert cart["shipping_cents"] == SHIPPING_PRICE_CENTS
    assert cart["total_cents"] == sum(prices.values()) + SHIPPING_PRICE_CENTS
    # Added again: the quantity changes, no second line.
    cart = _add(client, shop, a, quantity=3).json()
    assert cart["count"] == 3 and next(line for line in cart["items"] if line["album_id"] == a)["quantity"] == 3
    # Removed, changed.
    line = next(line for line in cart["items"] if line["kind"] == "digital")
    cart = client.delete(f"/api/cart/items/{line['id']}", headers=shop["headers"]).json()
    assert cart["count"] == 2
    line = next(line for line in cart["items"] if line["album_id"] == a)
    cart = client.patch(f"/api/cart/items/{line['id']}", json={"quantity": 1}, headers=shop["headers"]).json()
    assert next(line for line in cart["items"] if line["album_id"] == a)["quantity"] == 1


def test_a_pdf_only_cart_has_no_delivery_and_needs_no_address(client, shop, online_payment):
    a = shop["album"]("Byblos")
    cart = _add(client, shop, a, "digital").json()
    assert cart["shipping_cents"] == 0 and cart["total_cents"] == DIGITAL_PRICE_CENTS
    res = client.post("/api/cart/checkout", json={"accepted_terms_version": TERMS_VERSION}, headers=shop["headers"])
    assert res.status_code == 200, res.text
    (order,) = res.json()["orders"]
    assert order["kind"] == "digital" and order["status"] == "available"


def test_checkout_orders_everything_at_once(client, db, shop, online_payment):
    from app.services.print_groups import flush_printer_queue

    a, b = shop["album"]("Byblos"), shop["album"]("Tyre")
    _add(client, shop, a)
    _add(client, shop, b, quantity=2)
    _add(client, shop, b, "digital")
    # Not without the address (printed albums) nor the terms.
    assert client.post("/api/cart/checkout", json={"accepted_terms_version": TERMS_VERSION}, headers=shop["headers"]).status_code == 400
    assert _checkout(client, shop, accepted_terms_version="old").status_code == 400

    res = _checkout(client, shop)
    assert res.status_code == 200, res.text
    orders = res.json()["orders"]
    assert len(orders) == 3 and len({o["checkout_id"] for o in orders}) == 1
    prints = [o for o in orders if o["kind"] == "print"]
    # The delivery once, on one printed album.
    assert sorted(o["shipping_price_cents"] for o in prints) == [0, SHIPPING_PRICE_CENTS]
    assert sum(o["total_price_cents"] for o in prints) == compute_order_price_cents("A4", 24) * 3 + SHIPPING_PRICE_CENTS
    # One confirmation email, the cart emptied, the albums locked.
    assert len(shop["emails"]) == 1 and sorted(shop["emails"][0]) == sorted(o["id"] for o in orders)
    assert client.get("/api/cart", headers=shop["headers"]).json()["count"] == 0
    assert _add(client, shop, a).status_code == 409

    # The printed albums go to the printer together, in one package…
    for o in prints:
        assert _order(db, o["id"]).get("printer_pending_at")
    asyncio.run(flush_printer_queue(force_order_id=prints[0]["id"]))
    group = shop["courier"]["sent"]["printer"][-1]
    assert sorted(group) == sorted(o["id"] for o in prints)
    # …and to the courier: one delivery, the delivery charged once.
    lead = _order(db, group[0])
    assert _ready(client, lead["id"]).status_code == 200
    adds = [body for _, path, body in shop["courier"]["fake"].calls if "/add_delivery/" in path]
    assert len(adds) == 1 and len(adds[0]["packages"]) == 2
    totals = sum(_order(db, o["id"])["total_price_cents"] for o in prints)
    assert adds[0]["collection_amount"] == totals / 100 == (compute_order_price_cents("A4", 24) * 3 + SHIPPING_PRICE_CENTS) / 100


def test_a_cart_album_still_being_made_is_waited_for(client, db, shop):
    from datetime import datetime, timedelta, timezone

    from app.services.print_groups import flush_printer_queue

    a, b = shop["album"]("Byblos"), shop["album"]("Tyre")
    _add(client, shop, a)
    _add(client, shop, b)
    orders = _checkout(client, shop).json()["orders"]
    first, second = orders
    # The second one's PDF isn't made yet; the first has waited over an hour.
    long_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    asyncio.run(db.orders.update_one({"id": first["id"]}, {"$set": {"printer_pending_at": long_ago}}))
    asyncio.run(db.orders.update_one({"id": second["id"]}, {"$set": {"pdf_ready": False, "status": "pending_payment"}, "$unset": {"printer_pending_at": ""}}))
    sent_before = len(shop["courier"]["sent"].get("printer", []))
    asyncio.run(flush_printer_queue())
    assert len(shop["courier"]["sent"].get("printer", [])) == sent_before  # waits for the other one
    # Made: both go together.
    asyncio.run(db.orders.update_one({"id": second["id"]}, {"$set": {"pdf_ready": True, "status": "printing", "printer_pending_at": long_ago}}))
    asyncio.run(flush_printer_queue())
    assert sorted(shop["courier"]["sent"]["printer"][-1]) == sorted([first["id"], second["id"]])


def test_only_the_owners_albums_and_not_twice(client, db, shop):
    from tests.test_api import _signup

    a = shop["album"]("Byblos")
    _, stranger = _signup(client, db=db)
    assert client.post("/api/cart/items", json={"album_id": a, "kind": "print"}, headers=stranger).status_code == 404
    assert client.post("/api/cart/checkout", json={"accepted_terms_version": TERMS_VERSION}, headers=stranger).status_code == 400  # empty
    _add(client, shop, a)
    # Ordered meanwhile on its own: the cart says so, checkout refuses.
    asyncio.run(db.orders.insert_one({"id": "x-1", "album_id": a, "kind": "print", "user_id": "u", "status": "printing"}))
    cart = client.get("/api/cart", headers=shop["headers"]).json()
    assert cart["items"][0]["problem"] == "already_ordered" and cart["total_cents"] == 0
    assert _checkout(client, shop).status_code == 409


def test_one_confirmation_email_lists_everything(app, monkeypatch):
    from app.services import email as email_module

    sent = []
    monkeypatch.setattr(email_module, "send_email", lambda to, subject, body, html_body=None, reply_to=None: sent.append((subject, body, html_body)))
    orders = [
        {"id": "5f4c0509-1", "album_title": "Byblos", "kind": "print", "quantity": 2, "total_price_cents": 11100, "currency": "usd"},
        {"id": "6a1b0000-2", "album_title": "Tyre", "kind": "print", "quantity": 1, "total_price_cents": 5300, "currency": "usd"},
        {"id": "7c2d0000-3", "album_title": "Tyre", "kind": "digital", "quantity": 1, "total_price_cents": 2500, "currency": "usd"},
    ]
    email_module.send_checkout_confirmation_email("rita@example.com", "Rita", orders)
    (subject, body, html), = sent
    assert "3 items" in subject
    assert "Byblos — printed album × 2 (EB-5F4C0509)" in body and "Tyre — PDF to download (EB-7C2D0000)" in body
    assert "Payment is cash on delivery" in body and "164.00 USD (delivery included), is paid to the courier" in body and "one package" in body
    assert "nothing to pay for your PDF" in body and "Byblos" in html


def test_cash_on_delivery_only_for_now(client, shop):
    """Until Whish Pay / card: a printed album is ordered and paid cash on
    delivery; the PDF and gift cards are "coming soon" and can't be ordered."""
    album_id = shop["album"]("Summer")
    pdf = client.post("/api/cart/items", json={"album_id": album_id, "kind": "digital"}, headers=shop["headers"])
    assert pdf.status_code == 400 and "Whish" in pdf.json()["detail"]
    gift = client.post("/api/cart/gifts", json={"size": "A4", "page_tier": 24, "recipient_name": "Maya", "message": "", "from_name": "", "lang": "en"},
                       headers=shop["headers"])
    assert gift.status_code == 400
    single = client.post("/api/orders", json={"album_id": album_id, "kind": "digital", "quantity": 1, "accepted_terms_version": TERMS_VERSION},
                         headers=shop["headers"])
    assert single.status_code == 400
    cart = client.post("/api/cart/items", json={"album_id": album_id, "kind": "print", "quantity": 1}, headers=shop["headers"]).json()
    assert cart["cash_cents"] == cart["total_cents"] > 0
    placed = client.post("/api/cart/checkout", json={"shipping_address": ADDRESS, "accepted_terms_version": TERMS_VERSION}, headers=shop["headers"])
    assert placed.status_code == 200
    # Not paid: printed, then the courier collects the total.
    order = placed.json()["orders"][0]
    assert order["status_history"][0]["status"] == "pending_payment"
    assert all(h["status"] != "paid" for h in order["status_history"])


def test_a_pdf_left_in_a_cart_is_shown_as_coming_soon(client, db, shop):
    """Added before the switch: the line stays, marked "coming soon", out of
    the total, and the checkout asks to remove it."""
    album_id = shop["album"]("Winter")
    user_id = asyncio.run(db.albums.find_one({"id": album_id}))["user_id"]
    asyncio.run(db.carts.update_one({"user_id": user_id}, {"$set": {"items": [
        {"id": "p", "album_id": album_id, "kind": "print", "quantity": 1},
        {"id": "d", "album_id": album_id, "kind": "digital", "quantity": 1},
    ]}}, upsert=True))
    cart = client.get("/api/cart", headers=shop["headers"]).json()
    assert {i["kind"]: i["problem"] for i in cart["items"]} == {"print": None, "digital": "payment_soon"}
    assert cart["subtotal_cents"] == compute_order_price_cents("A4", 24)
    placed = client.post("/api/cart/checkout", json={"shipping_address": ADDRESS, "accepted_terms_version": TERMS_VERSION}, headers=shop["headers"])
    assert placed.status_code == 409
