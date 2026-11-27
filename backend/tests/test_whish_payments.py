"""Paying with Whish Pay: nothing is ordered before Whish confirms the
payment; paid, the albums go to the printer "paid" (nothing for the courier
to collect); failed, the cart stays; a cart changed meanwhile is sent to
the team, never ordered on a guess."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_cart import _add, shop  # noqa: F401  (fixture)
from tests.test_wakilni import ADDRESS, courier  # noqa: F401  (fixture)


def _body(**extra):
    from app.services.pricing import TERMS_VERSION

    return {"shipping_address": ADDRESS, "accepted_terms_version": TERMS_VERSION, **extra}


def _start(client, shop, **extra):  # noqa: F811
    res = client.post("/api/cart/checkout", json=_body(**extra), headers=shop["headers"])
    assert res.status_code == 200, res.text
    return res.json()["payment"]


def _orders_of(db, shop):  # noqa: F811
    """This test's customer's orders (the fixture's own one aside)."""
    user_id = shop["courier"]["order"]["user_id"]
    return asyncio.run(db.orders.find({"user_id": user_id, "id": {"$ne": shop["courier"]["order"]["id"]}}, {"_id": 0}).to_list(20))


# ---------- The Whish API client ----------

class _Resp:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def test_the_client_sends_the_keys_and_reads_the_answer(app, monkeypatch):
    from app import config
    from app.services import whish

    monkeypatch.setattr(config, "WHISH_CHANNEL", "chan")
    monkeypatch.setattr(config, "WHISH_SECRET", "sec")
    monkeypatch.setattr(config, "WHISH_WEBSITE_URL", "https://everbook-album.com")
    monkeypatch.setattr(config, "WHISH_ENV", "sandbox")
    calls = []

    def post(url, json=None, headers=None, timeout=None):
        calls.append((url, json, headers))
        if url.endswith("/payment/whish"):
            return _Resp({"status": True, "code": None, "data": {"collectUrl": "https://whish.money/pay/abc"}})
        return _Resp({"status": True, "code": None, "data": {"collectStatus": "success", "payerPhoneNumber": "961"}})

    monkeypatch.setattr(whish.requests, "post", post)
    assert whish.enabled()
    url = whish.create_payment(amount_cents=5300, external_id="ext-1", invoice="Everbook — Byblos",
                               success_callback="https://b/s", failure_callback="https://b/f",
                               success_redirect="https://f/s", failure_redirect="https://f/f")
    assert url == "https://whish.money/pay/abc"
    target, body, headers = calls[0]
    assert target == "https://partner.api.sbx.whish.money/itel-service/api/payment/whish"
    assert body["amount"] == "53.00" and body["currency"] == "USD" and body["externalId"] == "ext-1"
    assert headers["channel"] == "chan" and headers["secret"] == "sec" and headers["websiteUrl"] == "https://everbook-album.com"
    assert headers["User-Agent"].startswith("Everbook/")
    assert whish.payment_status("ext-1") == "success"
    assert calls[1][0].endswith("/payment/collect/status") and calls[1][1] == {"currency": "USD", "externalId": "ext-1"}
    monkeypatch.setattr(config, "WHISH_ENV", "production")
    whish.payment_status("ext-1")
    assert calls[2][0].startswith("https://api.whish.money/")


def test_the_client_tells_a_refusal_from_a_pending_answer(app, monkeypatch):
    from app.services import whish

    answers = iter([{"status": False, "code": "500", "data": None}, {"status": False, "code": "auth.session_not_exist", "data": None}])
    monkeypatch.setattr(whish.requests, "post", lambda *a, **k: _Resp(next(answers)))
    with pytest.raises(whish.WhishError) as pending:
        whish.payment_status("x")
    assert pending.value.code == "pending"
    with pytest.raises(whish.WhishError) as refused:
        whish.payment_status("x")
    assert refused.value.code == "auth.session_not_exist"


def test_without_the_keys_online_payment_is_off(app, monkeypatch):
    from app import config
    from app.services import whish

    monkeypatch.setattr(config, "WHISH_SECRET", None)
    assert not whish.enabled()


# ---------- Paying a cart ----------

def test_nothing_is_ordered_before_the_payment_then_everything_paid(client, db, shop, online_payment):  # noqa: F811
    _add(client, shop, shop["album"]("Byblos"))
    payment = _start(client, shop, payment_method="whish")
    assert payment["status"] == "pending" and payment["redirect_url"].startswith("https://whish.example/pay/")
    asked = online_payment.created[-1]
    assert asked["amount_cents"] == client.get("/api/cart", headers=shop["headers"]).json()["total_cents"]
    assert f"payment={payment['id']}" in asked["success_callback"] and "outcome=success" in asked["success_callback"]
    assert "/payment/return?payment=" in asked["success_redirect"]
    # Not paid yet: nothing ordered, the cart as it was.
    online_payment.outcome = "pending"
    assert client.get(f"/api/payments/{payment['id']}", headers=shop["headers"]).json()["status"] == "pending"
    assert _orders_of(db, shop) == []
    assert client.get("/api/cart", headers=shop["headers"]).json()["count"] == 1

    # Paid: Whish calls back, the cart is ordered — once, however many calls.
    online_payment.outcome = "success"
    for _ in range(2):
        assert client.get(f"/api/payments/whish/callback?payment={payment['id']}&outcome=success").text == "OK"
    after = client.get(f"/api/payments/{payment['id']}", headers=shop["headers"]).json()
    assert after["status"] == "placed" and len(after["orders"]) == 1
    (order,) = _orders_of(db, shop)
    # Paid, then on to the printer (the PDF is made at once in the tests).
    assert [h["status"] for h in order["status_history"]][:2] == ["paid", "printing"]
    assert order["payment"]["provider"] == "whish"
    assert client.get("/api/cart", headers=shop["headers"]).json()["count"] == 0
    # The courier collects nothing for it.
    from app.services.wakilni import delivery_payload

    assert delivery_payload(order, {})["collection_amount"] == 0


def test_a_failed_payment_orders_nothing_and_keeps_the_cart(client, db, shop, online_payment):  # noqa: F811
    _add(client, shop, shop["album"]("Byblos"))
    payment = _start(client, shop, payment_method="whish")
    online_payment.outcome = "failed"
    client.get(f"/api/payments/whish/callback?payment={payment['id']}&outcome=failure")
    assert client.get(f"/api/payments/{payment['id']}", headers=shop["headers"]).json()["status"] == "failed"
    assert _orders_of(db, shop) == []
    assert client.get("/api/cart", headers=shop["headers"]).json()["count"] == 1


def test_cash_on_delivery_still_orders_at_once(client, db, shop, online_payment):  # noqa: F811
    _add(client, shop, shop["album"]("Byblos"))
    res = client.post("/api/cart/checkout", json=_body(payment_method="cod"), headers=shop["headers"])
    assert res.status_code == 200 and "payment" not in res.json()
    (order,) = _orders_of(db, shop)
    assert order["status_history"][0]["status"] == "pending_payment" and "payment" not in order
    assert "paid" not in [h["status"] for h in order["status_history"]]
    assert online_payment.created == []


def test_a_gift_card_or_a_pdf_is_only_paid_online(client, db, shop, online_payment):  # noqa: F811
    from app.services.pricing import TERMS_VERSION

    _add(client, shop, shop["album"]("Byblos"), "digital")
    res = client.post("/api/cart/checkout", json={"accepted_terms_version": TERMS_VERSION, "payment_method": "cod"}, headers=shop["headers"])
    assert res.status_code == 400
    # Without a choice: Whish.
    res = client.post("/api/cart/checkout", json={"accepted_terms_version": TERMS_VERSION}, headers=shop["headers"])
    assert "payment" in res.json()


def test_whish_unreachable_orders_nothing(client, db, shop, online_payment):  # noqa: F811
    _add(client, shop, shop["album"]("Byblos"))
    online_payment.down = True
    res = client.post("/api/cart/checkout", json=_body(payment_method="whish"), headers=shop["headers"])
    assert res.status_code == 502
    assert _orders_of(db, shop) == []


def test_a_cart_changed_after_paying_goes_to_the_team(client, db, shop, online_payment, monkeypatch):  # noqa: F811
    from app.routers import payments as payments_router

    reviews = []
    monkeypatch.setattr(payments_router, "send_payment_review_email", lambda payment, customer, problem: reviews.append(problem))
    _add(client, shop, shop["album"]("Byblos"))
    payment = _start(client, shop, payment_method="whish")
    # Another album added in another tab, then the first payment goes through.
    _add(client, shop, shop["album"]("Tyre"))
    client.get(f"/api/payments/whish/callback?payment={payment['id']}&outcome=success")
    assert client.get(f"/api/payments/{payment['id']}", headers=shop["headers"]).json()["status"] == "needs_review"
    assert _orders_of(db, shop) == []
    assert reviews and "changed" in reviews[0]


def test_the_scheduled_check_settles_what_nobody_came_back_for(client, db, shop, online_payment):  # noqa: F811
    from app.routers.payments import reconcile_payments

    _add(client, shop, shop["album"]("Byblos"))
    paid = _start(client, shop, payment_method="whish")
    # The customer closed the page; Whish's callback never came.
    result = asyncio.run(reconcile_payments())
    assert result["payments_settled"] >= 1
    assert asyncio.run(db.payments.find_one({"id": paid["id"]}))["status"] == "placed"
    assert len(_orders_of(db, shop)) == 1

    # A payment left pending for over a day is given up.
    _add(client, shop, shop["album"]("Tyre"))
    old = _start(client, shop, payment_method="whish")
    long_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    asyncio.run(db.payments.update_one({"id": old["id"]}, {"$set": {"created_at": long_ago}}))
    online_payment.outcome = "pending"
    asyncio.run(reconcile_payments())
    assert asyncio.run(db.payments.find_one({"id": old["id"]}))["status"] == "expired"


def test_a_payment_is_only_seen_by_its_owner(client, db, shop, online_payment):  # noqa: F811
    from tests.test_api import _signup

    _add(client, shop, shop["album"]("Byblos"))
    payment = _start(client, shop, payment_method="whish")
    _, stranger = _signup(client, db=db)
    assert client.get(f"/api/payments/{payment['id']}", headers=stranger).status_code == 404
    # An unknown payment in a callback: answered, nothing done.
    assert client.get("/api/payments/whish/callback?payment=nope&outcome=success").status_code == 200


def test_the_emails_say_it_is_paid_not_to_pay_the_courier(app, monkeypatch):
    from app.services import email

    sent = []
    monkeypatch.setattr(email, "send_email", lambda to, subject, body, html_body=None, **k: sent.append(body))
    paid = {"id": "o-paid-1", "kind": "print", "album_title": "Byblos", "quantity": 1, "unit_price_cents": 5300, "total_price_cents": 5800,
            "shipping_price_cents": 500, "currency": "usd", "payment": {"provider": "whish"}, "shipping_address": {}}
    email.send_order_confirmation_email("c@example.com", "C", paid)
    email.send_checkout_confirmation_email("c@example.com", "C", [paid, {**paid, "id": "o-paid-2", "kind": "digital"}])
    assert all("Whish Pay" in body and "cash to the courier" not in body and "cash on delivery" not in body for body in sent)
    monkeypatch.setattr(email, "ADMIN_EMAIL", "team@example.com")
    email.send_team_new_order_email([paid], {"name": "C", "email": "c@example.com"})
    assert "To collect in cash by the courier: 0.00 USD" in sent[-1] and "Paid online (Whish Pay)" in sent[-1]


def test_a_failed_attempt_is_closed_at_once_but_a_late_success_still_orders(client, db, shop, online_payment):  # noqa: F811
    from app.routers.payments import reconcile_payments

    _add(client, shop, shop["album"]("Byblos"))
    payment = _start(client, shop, payment_method="whish")
    # Whish keeps a failed attempt "pending" until the link expires; its
    # failure callback (or the failure page) closes it here.
    online_payment.outcome = "pending"
    client.get(f"/api/payments/whish/callback?payment={payment['id']}&outcome=failure")
    assert client.get(f"/api/payments/{payment['id']}", headers=shop["headers"]).json()["status"] == "failed"
    assert _orders_of(db, shop) == []
    # Paid after all (Whish says so later): the scheduled check orders it.
    online_payment.outcome = "success"
    asyncio.run(reconcile_payments())
    assert asyncio.run(db.payments.find_one({"id": payment["id"]}))["status"] == "placed"
    assert len(_orders_of(db, shop)) == 1


def test_the_failure_page_closes_the_attempt_unless_whish_says_paid(client, db, shop, online_payment):  # noqa: F811
    _add(client, shop, shop["album"]("Byblos"))
    payment = _start(client, shop, payment_method="whish")
    online_payment.outcome = "success"
    # Sent to the failure page, but Whish says paid: paid wins.
    res = client.get(f"/api/payments/{payment['id']}?outcome=failure", headers=shop["headers"]).json()
    assert res["status"] == "placed"


# ---------- Cash on delivery switched off (the site now) ----------

from app.services.pricing import TERMS_VERSION  # noqa: E402


def _no_cash_on_delivery(monkeypatch):
    """As the site is now (the fixtures' own orders are placed before)."""
    from app.services import payments

    monkeypatch.setattr(payments, "CASH_ON_DELIVERY", False)


def test_without_cash_on_delivery_a_printed_album_is_paid_online(client, db, shop, online_payment, monkeypatch):  # noqa: F811
    from tests.conftest import checkout as pay

    _no_cash_on_delivery(monkeypatch)

    album_id = shop["album"]("Byblos")
    cart = client.post("/api/cart/items", json={"album_id": album_id, "kind": "print", "quantity": 1}, headers=shop["headers"]).json()
    assert cart["cash_on_delivery"] is False and cart["needs_online_payment"] is True
    body = {"shipping_address": ADDRESS, "accepted_terms_version": TERMS_VERSION}
    # Asking to pay on delivery: refused, nothing ordered.
    cod = client.post("/api/cart/checkout", json={**body, "payment_method": "cod"}, headers=shop["headers"])
    assert cod.status_code == 400 and "on delivery" in cod.json()["detail"]
    # Nor through the old single-album route.
    single = client.post("/api/orders", json={"album_id": album_id, **body}, headers=shop["headers"])
    assert single.status_code == 400
    # No method given: Whish Pay, and once paid, nothing for the courier.
    placed = pay(client, json=body, headers=shop["headers"])
    assert placed.status_code == 200
    (order,) = placed.json()["orders"]
    assert order["status_history"][0]["status"] == "paid" and order["payment"]["provider"] == "whish"
    from app.services.wakilni import delivery_payload

    assert delivery_payload(order, {})["collection_amount"] == 0


def test_without_cash_on_delivery_a_cart_with_nothing_to_pay_is_ordered_at_once(client, db, shop, online_payment, monkeypatch):  # noqa: F811
    _no_cash_on_delivery(monkeypatch)
    album_id = shop["album"]("Tyre")
    client.post("/api/cart/items", json={"album_id": album_id, "kind": "digital"}, headers=shop["headers"])
    asyncio.run(db.promo_codes.insert_one({"code": "ALLFREE", "percent": 100, "active": True}))
    assert client.post("/api/cart/promo", json={"code": "ALLFREE"}, headers=shop["headers"]).status_code == 200
    res = client.post("/api/cart/checkout", json={"accepted_terms_version": TERMS_VERSION, "payment_method": "cod"}, headers=shop["headers"])
    assert res.status_code == 200 and "payment" not in res.json()
    (order,) = res.json()["orders"]
    assert order["status_history"][0]["status"] == "paid"
