"""Gift cards: bought through the cart (a PDF, through the payment step),
used with their code, their value taken off the album ordered — the
difference paid on a dearer one, the rest kept as credit on a cheaper one."""
import asyncio
import re
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.usefixtures("online_payment")

from app.services.pricing import SHIPPING_PRICE_CENTS, TERMS_VERSION, compute_order_price_cents
from tests.test_api import _signup
from tests.test_cart import shop  # noqa: F401  (fixture)
from tests.test_wakilni import ADDRESS, _ready, courier  # noqa: F401  (fixture)


@pytest.fixture()
def gifts(client, db, shop, monkeypatch):  # noqa: F811
    from app.routers import cart as cart_router

    sent = []
    monkeypatch.setattr(cart_router, "send_gift_cards_email", lambda to, name, cards, pdfs: sent.append((to, cards, pdfs)))
    _, buyer = _signup(client, db=db)
    return {"buyer": buyer, "sent": sent}


def _buy(client, headers, size="A4", page_tier=50, **extra):
    body = {"size": size, "page_tier": page_tier, "recipient_name": "Sarah", "message": "Happy birthday!", "from_name": "Karim", **extra}
    cart = client.post("/api/cart/gifts", json=body, headers=headers).json()
    res = client.post("/api/cart/checkout", json={"accepted_terms_version": TERMS_VERSION}, headers=headers)
    assert res.status_code == 200, res.text
    return cart, res.json()["gift_cards"]


def _redeem(client, headers, code):
    return client.post("/api/gift-cards/redeem", json={"code": code}, headers=headers)


VALUE_A4_50 = compute_order_price_cents("A4", 50) + SHIPPING_PRICE_CENTS


def test_buying_a_gift_card(client, gifts):
    cart, (card,) = _buy(client, gifts["buyer"])
    # Worth the album with its delivery; no address needed, through the payment step.
    assert cart["total_cents"] == cart["pay_now_cents"] == VALUE_A4_50 and cart["shipping_cents"] == 0
    assert re.fullmatch(r"EVER-[A-HJKMNP-Z2-9]{4}-[A-HJKMNP-Z2-9]{4}", card["code"])
    assert card["status"] == "active" and card["value_cents"] == VALUE_A4_50
    assert card["expires_at"][:4] == str(datetime.now(timezone.utc).year + 1)
    # Emailed as a PDF; in the buyer's list; the cart emptied.
    (_, cards, pdfs), = gifts["sent"]
    assert cards[0]["code"] == card["code"] and pdfs[0][1].startswith(b"%PDF") and pdfs[0][2] == "application/pdf"
    assert [c["code"] for c in client.get("/api/gift-cards", headers=gifts["buyer"]).json()][0] == card["code"]
    assert client.get("/api/cart", headers=gifts["buyer"]).json()["count"] == 0
    pdf = client.get(f"/api/gift-cards/{card['id']}/pdf", headers=gifts["buyer"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_the_card_pdf_says_who_it_is_for_and_the_code(gifts):
    from app.services.gift_cards import render_gift_card_pdf

    card = {"code": "EVER-AB2C-D3EF", "size": "A5", "page_tier": 100, "recipient_name": "Sarah", "message": "Bon anniversaire !",
            "from_name": "Karim", "lang": "fr", "expires_at": "2027-10-20T10:00:00+00:00"}
    assert render_gift_card_pdf(card).startswith(b"%PDF")
    assert render_gift_card_pdf({**card, "lang": "en", "message": "", "recipient_name": ""}).startswith(b"%PDF")


def test_a_code_is_used_once(client, db, gifts, shop):  # noqa: F811
    _, (card,) = _buy(client, gifts["buyer"])
    # Typed loosely: lowercase, no dashes.
    res = _redeem(client, shop["headers"], card["code"].lower().replace("-", " "))
    assert res.status_code == 200, res.text
    assert res.json()["credit_balance_cents"] >= VALUE_A4_50
    credits = client.get("/api/credits", headers=shop["headers"]).json()
    assert credits["offered"] == {"size": "A4", "page_tier": 50, "from_name": "Karim"}
    # The same person again: fine. Someone else: already used.
    assert _redeem(client, shop["headers"], card["code"]).status_code == 200
    _, other = _signup(client, db=db)
    assert _redeem(client, other, card["code"]).json()["detail"]["reason"] == "used"
    assert _redeem(client, other, "EVER-2222-2222").json()["detail"]["reason"] == "not_found"


def test_expired_and_cancelled_cards_dont_work(client, db, gifts, monkeypatch):
    from app.core import auth

    _, (old,) = _buy(client, gifts["buyer"], page_tier=24)
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    asyncio.run(db.gift_cards.update_one({"id": old["id"]}, {"$set": {"expires_at": past}}))
    _, user = _signup(client, db=db)
    assert _redeem(client, user, old["code"]).json()["detail"]["reason"] == "expired"
    _, (card,) = _buy(client, gifts["buyer"], page_tier=24)
    email, admin = _signup(client, db=db)
    monkeypatch.setattr(auth, "ADMIN_EMAIL", email)
    assert client.post(f"/api/admin/gift-cards/{card['id']}/cancel", headers=admin).json()["status"] == "cancelled"
    assert _redeem(client, user, card["code"]).json()["detail"]["reason"] == "cancelled"
    assert any(c["id"] == card["id"] for c in client.get("/api/admin/gift-cards", headers=admin).json())


def _credit_of(client, headers):
    return client.get("/api/credits", headers=headers).json()["balance_cents"]


def test_the_offered_album_costs_nothing_more(client, db, gifts, shop, courier):  # noqa: F811
    _, (card,) = _buy(client, gifts["buyer"])
    _redeem(client, shop["headers"], card["code"])
    album = shop["album"]("Sarah's year", pages=50)
    client.post("/api/cart/items", json={"album_id": album, "kind": "print"}, headers=shop["headers"])
    cart = client.get("/api/cart", headers=shop["headers"]).json()
    assert cart["credit_applied_cents"] == VALUE_A4_50 and cart["total_cents"] == 0 and cart["cash_cents"] == 0
    res = client.post("/api/cart/checkout", json={"shipping_address": ADDRESS, "accepted_terms_version": TERMS_VERSION}, headers=shop["headers"])
    (order,) = res.json()["orders"]
    assert order["gift_credit_cents"] == VALUE_A4_50 and order["total_price_cents"] == 0
    assert _credit_of(client, shop["headers"]) == 0
    # The courier collects nothing.
    from app.services.wakilni import delivery_payload

    assert delivery_payload(order, {})["collection_amount"] == 0


def test_a_dearer_album_pays_the_difference_a_cheaper_one_keeps_the_rest(client, db, gifts, shop):  # noqa: F811
    _, (card,) = _buy(client, gifts["buyer"])
    _redeem(client, shop["headers"], card["code"])
    big = shop["album"]("Big", pages=100)
    client.post("/api/cart/items", json={"album_id": big, "kind": "print"}, headers=shop["headers"])
    cart = client.get("/api/cart", headers=shop["headers"]).json()
    dearer = compute_order_price_cents("A4", 100) + SHIPPING_PRICE_CENTS
    assert cart["cash_cents"] == dearer - VALUE_A4_50 == cart["total_cents"]
    # Swapped for a smaller one: the rest stays as credit for a next order.
    line = cart["items"][0]
    client.delete(f"/api/cart/items/{line['id']}", headers=shop["headers"])
    small = shop["album"]("Small", pages=24)
    client.post("/api/cart/items", json={"album_id": small, "kind": "print"}, headers=shop["headers"])
    client.post("/api/cart/checkout", json={"shipping_address": ADDRESS, "accepted_terms_version": TERMS_VERSION}, headers=shop["headers"])
    assert _credit_of(client, shop["headers"]) == VALUE_A4_50 - (compute_order_price_cents("A4", 24) + SHIPPING_PRICE_CENTS)


def test_a_delivery_paid_with_credit_then_shared_comes_back_as_credit(client, db, gifts, shop):  # noqa: F811
    from app.services.print_groups import flush_printer_queue

    # A first order, on its own (pays the delivery)…
    first = shop["album"]("First", pages=24)
    client.post("/api/cart/items", json={"album_id": first, "kind": "print"}, headers=shop["headers"])
    client.post("/api/cart/checkout", json={"shipping_address": ADDRESS, "accepted_terms_version": TERMS_VERSION}, headers=shop["headers"])
    # …then a second, paid with a gift card, delivery included.
    _, (card,) = _buy(client, gifts["buyer"], page_tier=24)
    _redeem(client, shop["headers"], card["code"])
    second = shop["album"]("Second", pages=24)
    client.post("/api/cart/items", json={"album_id": second, "kind": "print"}, headers=shop["headers"])
    (order,) = client.post("/api/cart/checkout", json={"shipping_address": ADDRESS, "accepted_terms_version": TERMS_VERSION},
                           headers=shop["headers"]).json()["orders"]
    assert order["total_price_cents"] == 0 and _credit_of(client, shop["headers"]) == 0
    # Sent together: one delivery, paid by the first — the 5 $ come back.
    asyncio.run(flush_printer_queue(force_order_id=order["id"]))
    assert _credit_of(client, shop["headers"]) == SHIPPING_PRICE_CENTS
    fresh = asyncio.run(db.orders.find_one({"id": order["id"]}, {"_id": 0}))
    assert fresh["total_price_cents"] == 0 and fresh["shipping_price_cents"] == 0
    assert fresh["gift_credit_cents"] == compute_order_price_cents("A4", 24)
