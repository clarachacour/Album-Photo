"""Paying by card (Cybersource Unified Checkout, through areeba): signed
calls as areeba's guide describes; the card form's result is only a
transaction id — the transaction is read from Cybersource before anything
is ordered, captured if only authorized; a refusal, a different amount or a
transaction used twice orders nothing."""
import asyncio
import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_cart import _add, shop  # noqa: F401  (fixture)
from tests.test_wakilni import ADDRESS, courier  # noqa: F401  (fixture)


def _jwt(payload: dict) -> str:
    part = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJSUzI1NiJ9.{part}.sig"


class FakeCybersource:
    """Transactions as Cybersource would list them, by id."""

    def __init__(self):
        self.sessions = []
        self.transactions = {}
        self.captured = []
        self.by_reference = {}

    def create_session(self, amount_cents, origins, reference, locale="en_US"):
        self.sessions.append({"amount_cents": amount_cents, "origins": origins, "reference": reference, "locale": locale})
        return _jwt({"ctx": [{"data": {"clientLibrary": "https://testup.cybersource.com/uc/v1/assets/sdk.js"}}]})

    def pay(self, tx_id, amount, reference, captured=True, approved=True):
        apps = [{"name": "ics_auth", "rCode": 1 if approved else 0}]
        if captured and approved:
            apps.append({"name": "ics_bill", "rCode": 1})
        self.transactions[tx_id] = {
            "id": tx_id,
            "clientReferenceInformation": {"code": reference},
            "orderInformation": {"amountDetails": {"totalAmount": f"{amount:.2f}", "authorizedAmount": f"{amount:.2f}", "currency": "USD"}},
            "applicationInformation": {"applications": apps},
        }
        self.by_reference[reference] = tx_id

    def transaction(self, tx_id):
        return self.transactions.get(tx_id)

    def capture(self, tx_id, amount_cents, reference):
        self.captured.append(tx_id)
        return {"status": "PENDING"}

    def find_by_reference(self, reference):
        return self.by_reference.get(reference)


@pytest.fixture()
def card(app, monkeypatch, online_payment):
    from app.services import cybersource, payments

    monkeypatch.setattr(payments, "CARD_PAYMENT", True)
    fake = FakeCybersource()
    for name in ("create_session", "transaction", "capture", "find_by_reference"):
        monkeypatch.setattr(cybersource, name, getattr(fake, name))
    return fake


def _body(**extra):
    from app.services.pricing import TERMS_VERSION

    return {"shipping_address": ADDRESS, "accepted_terms_version": TERMS_VERSION, "payment_method": "card", **extra}


def _start(client, shop):  # noqa: F811
    res = client.post("/api/cart/checkout", json=_body(), headers=shop["headers"])
    assert res.status_code == 200, res.text
    return res.json()["payment"]


def _orders_of(db, shop):  # noqa: F811
    user_id = shop["courier"]["order"]["user_id"]
    return asyncio.run(db.orders.find({"user_id": user_id, "id": {"$ne": shop["courier"]["order"]["id"]}}, {"_id": 0}).to_list(20))


def _result(client, shop, payment, tx_id):  # noqa: F811
    return client.post(f"/api/payments/{payment['id']}/card", json={"result": _jwt({"id": tx_id, "status": "AUTHORIZED"})},
                       headers=shop["headers"])


# ---------- The signed calls (areeba's guide, step 1) ----------

def test_calls_are_signed_as_the_guide_says(app, monkeypatch):
    from app import config
    from app.services import cybersource

    secret = base64.b64encode(b"the-shared-secret").decode()
    monkeypatch.setattr(config, "CYBS_MERCHANT_ID", "effet_design")
    monkeypatch.setattr(config, "CYBS_KEY_ID", "key-123")
    monkeypatch.setattr(config, "CYBS_SHARED_SECRET", secret)
    monkeypatch.setattr(config, "CYBS_ENV", "test")
    body = '{"targetOrigins":["https://everbook-album.com"]}'
    date = "Tue, 15 Apr 2025 12:00:00 GMT"
    headers = cybersource.signed_headers("POST", "/uc/v1/sessions", body, date)
    digest = "SHA-256=" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
    assert headers["host"] == "apitest.cybersource.com" and headers["date"] == date
    assert headers["v-c-merchant-id"] == "effet_design" and headers["digest"] == digest
    signed = f"host: apitest.cybersource.com\ndate: {date}\n(request-target): post /uc/v1/sessions\ndigest: {digest}\nv-c-merchant-id: effet_design"
    expected = base64.b64encode(hmac.new(b"the-shared-secret", signed.encode(), hashlib.sha256).digest()).decode()
    assert headers["signature"] == (
        f'keyid="key-123", algorithm="HmacSHA256", headers="host date (request-target) digest v-c-merchant-id", signature="{expected}"'
    )
    # A call without a body: no digest.
    get = cybersource.signed_headers("GET", "/tss/v2/transactions/1", None, date)
    assert "digest" not in get and 'headers="host date (request-target) v-c-merchant-id"' in get["signature"]
    monkeypatch.setattr(config, "CYBS_ENV", "production")
    assert cybersource.signed_headers("GET", "/x")["host"] == "api.cybersource.com"


def test_the_session_request_follows_the_guide(app, monkeypatch):
    from app import config
    from app.services import cybersource

    monkeypatch.setattr(config, "CYBS_MERCHANT_ID", "m")
    monkeypatch.setattr(config, "CYBS_KEY_ID", "k")
    monkeypatch.setattr(config, "CYBS_SHARED_SECRET", base64.b64encode(b"s").decode())
    sent = []

    class Resp:
        status_code = 201
        text = "aaa.bbb.ccc"

    monkeypatch.setattr(cybersource.requests, "request", lambda method, url, data=None, headers=None, timeout=None: sent.append((method, url, json.loads(data))) or Resp())
    assert cybersource.create_session(5300, ["https://everbook-album.com"], "pay-1") == "aaa.bbb.ccc"
    method, url, body = sent[0]
    assert method == "POST" and url == "https://apitest.cybersource.com/uc/v1/sessions"
    assert body["targetOrigins"] == ["https://everbook-album.com"] and body["country"] == "LB"
    assert body["data"]["orderInformation"]["amountDetails"] == {"totalAmount": "53.00", "currency": "USD"}


def test_a_refused_session_is_logged_whole_without_the_secret(app, monkeypatch, caplog):
    from app import config
    from app.services import cybersource

    secret = base64.b64encode(b"never-in-the-logs").decode()
    monkeypatch.setattr(config, "CYBS_MERCHANT_ID", "m")
    monkeypatch.setattr(config, "CYBS_KEY_ID", "k")
    monkeypatch.setattr(config, "CYBS_SHARED_SECRET", secret)

    class Resp:
        status_code = 404
        text = '{"responseStatus":{"status":404,"reason":"NOT_FOUND","message":"Profile for merchant not found"}}'
        headers = {"v-c-correlation-id": "corr-1"}

    monkeypatch.setattr(cybersource.requests, "request", lambda *a, **k: Resp())
    with caplog.at_level("WARNING"), pytest.raises(cybersource.CybersourceError):
        cybersource.create_session(5300, ["https://everbook-album.com"], "pay-1")
    (line,) = [r.getMessage() for r in caplog.records if "Diagnostic Cybersource" in r.getMessage()]
    logged = json.loads(line.split(": ", 1)[1])
    assert logged["endpoint"] == "POST https://apitest.cybersource.com/uc/v1/sessions"
    assert logged["request_body"]["targetOrigins"] == ["https://everbook-album.com"]
    assert "signature" in logged["request_headers"] and logged["response_headers"]["v-c-correlation-id"] == "corr-1"
    assert "Profile for merchant not found" in logged["response_body"]
    assert secret not in line and "never-in-the-logs" not in line


def test_reading_a_transaction(app):
    from app.services import cybersource

    fake = FakeCybersource()
    fake.pay("t1", 58, "p1")
    fake.pay("t2", 58, "p2", captured=False)
    fake.pay("t3", 58, "p3", approved=False)
    paid, held, refused = (cybersource.read_transaction(fake.transactions[t]) for t in ("t1", "t2", "t3"))
    assert paid["authorized"] and paid["captured"] and paid["amount_cents"] == 5800 and paid["currency"] == "USD" and paid["reference"] == "p1"
    assert held["authorized"] and not held["captured"]
    assert refused["declined"] and not refused["authorized"]
    assert cybersource.result_transaction_id(_jwt({"id": "t9"})) == "t9"
    assert cybersource.result_transaction_id("not a jwt") is None


# ---------- Paying a cart by card ----------

def test_paid_by_card_only_once_cybersource_says_so(client, db, shop, card):  # noqa: F811
    _add(client, shop, shop["album"]("Byblos"))
    payment = _start(client, shop)
    assert payment["provider"] == "card" and payment["session"].count(".") == 2
    total = client.get("/api/cart", headers=shop["headers"]).json()["total_cents"]
    assert card.sessions[-1]["amount_cents"] == total and card.sessions[-1]["reference"] == payment["id"]
    assert _orders_of(db, shop) == []
    # The browser says "paid" for a transaction Cybersource doesn't know: nothing.
    assert _result(client, shop, payment, "unknown-tx").json()["status"] == "pending"
    assert _orders_of(db, shop) == []


def test_a_captured_payment_orders_the_cart(client, db, shop, card):  # noqa: F811
    _add(client, shop, shop["album"]("Byblos"))
    payment = _start(client, shop)
    card.pay("tx-1", payment["amount_cents"] / 100, payment["id"])
    assert _result(client, shop, payment, "tx-1").json()["status"] == "placed"
    (order,) = _orders_of(db, shop)
    assert order["payment"]["provider"] == "card" and order["payment"]["reference"] == "tx-1"
    assert order["status_history"][0]["status"] == "paid" and card.captured == []
    from app.services.wakilni import delivery_payload

    assert delivery_payload(order, {})["collection_amount"] == 0


def test_an_authorization_only_is_captured(client, db, shop, card):  # noqa: F811
    _add(client, shop, shop["album"]("Byblos"))
    payment = _start(client, shop)
    card.pay("tx-2", payment["amount_cents"] / 100, payment["id"], captured=False)
    assert _result(client, shop, payment, "tx-2").json()["status"] == "placed"
    assert card.captured == ["tx-2"]


def test_a_refused_card_orders_nothing(client, db, shop, card):  # noqa: F811
    _add(client, shop, shop["album"]("Byblos"))
    payment = _start(client, shop)
    card.pay("tx-3", payment["amount_cents"] / 100, payment["id"], approved=False)
    assert _result(client, shop, payment, "tx-3").json()["status"] == "failed"
    assert _orders_of(db, shop) == []
    assert client.get("/api/cart", headers=shop["headers"]).json()["count"] == 1


def test_another_amount_goes_to_the_team(client, db, shop, card, monkeypatch):  # noqa: F811
    from app.routers import payments as payments_router

    reviews = []
    monkeypatch.setattr(payments_router, "send_payment_review_email", lambda payment, customer, problem: reviews.append(problem))
    _add(client, shop, shop["album"]("Byblos"))
    payment = _start(client, shop)
    card.pay("tx-4", 1.00, payment["id"])  # paid $1, not the cart's total
    assert _result(client, shop, payment, "tx-4").json()["status"] == "needs_review"
    assert _orders_of(db, shop) == [] and reviews


def test_a_transaction_pays_for_one_payment_only(client, db, shop, card):  # noqa: F811
    _add(client, shop, shop["album"]("Byblos"))
    first = _start(client, shop)
    card.pay("tx-5", first["amount_cents"] / 100, first["id"], approved=False)
    _result(client, shop, first, "tx-5")
    second = _start(client, shop)
    assert _result(client, shop, second, "tx-5").status_code == 409


def test_closing_the_card_form_cancels(client, db, shop, card):  # noqa: F811
    _add(client, shop, shop["album"]("Byblos"))
    payment = _start(client, shop)
    res = client.post(f"/api/payments/{payment['id']}/card", json={"cancelled": True}, headers=shop["headers"])
    assert res.json()["status"] == "cancelled"
    assert client.get("/api/cart", headers=shop["headers"]).json()["count"] == 1


def test_a_payment_the_browser_never_reported_is_found_later(client, db, shop, card):  # noqa: F811
    from app.routers.payments import reconcile_payments

    _add(client, shop, shop["album"]("Byblos"))
    payment = _start(client, shop)
    card.pay("tx-6", payment["amount_cents"] / 100, payment["id"])
    # Paid, then the page was closed before the result reached the server.
    asyncio.run(reconcile_payments())
    assert asyncio.run(db.payments.find_one({"id": payment["id"]}))["status"] == "pending"  # too soon to look
    earlier = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    asyncio.run(db.payments.update_one({"id": payment["id"]}, {"$set": {"created_at": earlier}}))
    asyncio.run(reconcile_payments())
    assert asyncio.run(db.payments.find_one({"id": payment["id"]}))["status"] == "placed"
    assert len(_orders_of(db, shop)) == 1


def test_card_needs_its_keys(client, shop, online_payment, monkeypatch):  # noqa: F811
    from app.services import payments

    monkeypatch.setattr(payments, "CARD_PAYMENT", False)
    _add(client, shop, shop["album"]("Byblos"))
    assert client.post("/api/cart/checkout", json=_body(), headers=shop["headers"]).status_code == 400
