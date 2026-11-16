"""Card payment (Cybersource Unified Checkout, through areeba): the card
form opened for the cart's total, the card charged when the order is placed
— for the amount computed here, once, and only for the cart as it was when
the form opened."""
import asyncio
import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.services.pricing import DIGITAL_PRICE_CENTS, SHIPPING_PRICE_CENTS, TERMS_VERSION, compute_order_price_cents
from tests.conftest import pay_by_card
from tests.test_cart import _add, shop  # noqa: F401  (fixture)
from tests.test_wakilni import ADDRESS, courier  # noqa: F401  (fixture)

BODY = {"shipping_address": ADDRESS, "accepted_terms_version": TERMS_VERSION}
PRINT_24 = compute_order_price_cents("A4", 24)


@pytest.fixture()
def team(monkeypatch):
    from app.services import email

    told = []
    monkeypatch.setattr(email, "send_team_payment_problem_email", lambda payment, customer, what: told.append(what))
    return told


def _session(client, shop, body=BODY):
    return client.post("/api/cart/card-session", json=body, headers=shop["headers"])


def _pay(client, shop, payment_id, body=BODY):
    return client.post("/api/cart/checkout", json={**body, "payment_method": "card", "payment_id": payment_id,
                                                   "transient_token": "transient.token.jwt"}, headers=shop["headers"])


def _payment(db, payment_id):
    return asyncio.run(db.payments.find_one({"id": payment_id}, {"_id": 0}))


# ---------- The Cybersource requests ----------

def test_requests_are_signed_with_the_shared_secret(monkeypatch):
    from app.services import cybersource

    secret = base64.b64encode(b"a shared secret").decode()
    monkeypatch.setattr(cybersource, "CYBERSOURCE_MERCHANT_ID", "everbook_test")
    monkeypatch.setattr(cybersource, "CYBERSOURCE_KEY_ID", "key-123")
    monkeypatch.setattr(cybersource, "CYBERSOURCE_SECRET_KEY", secret)
    monkeypatch.setattr(cybersource, "CYBERSOURCE_HOST", "apitest.cybersource.com")
    body = b'{"a":1}'
    date = "Mon, 16 Nov 2026 10:00:00 GMT"
    headers = cybersource.signed_headers("POST", "/pts/v2/payments", body, date=date)
    digest = "SHA-256=" + base64.b64encode(hashlib.sha256(body).digest()).decode()
    assert headers["digest"] == digest and headers["v-c-merchant-id"] == "everbook_test"
    signed = (f"host: apitest.cybersource.com\ndate: {date}\nrequest-target: post /pts/v2/payments\n"
              f"digest: {digest}\nv-c-merchant-id: everbook_test")
    expected = base64.b64encode(hmac.new(b"a shared secret", signed.encode(), hashlib.sha256).digest()).decode()
    assert headers["signature"] == (f'keyid="key-123", algorithm="HmacSHA256", '
                                    f'headers="host date request-target digest v-c-merchant-id", signature="{expected}"')
    # A GET has no body, so no digest.
    assert 'headers="host date request-target v-c-merchant-id"' in cybersource.signed_headers("GET", "/x", date=date)["signature"]


class _Answer:
    def __init__(self, status, data=None, text=None):
        self.status_code, self._data = status, data
        self.text = text if text is not None else json.dumps(data)

    def json(self):
        if self._data is None:
            raise ValueError
        return self._data


def _fake_post(monkeypatch, answer):
    from app.services import cybersource

    monkeypatch.setattr(cybersource, "CYBERSOURCE_SECRET_KEY", base64.b64encode(b"s").decode())
    calls = []

    def post(url, data, headers, timeout):
        calls.append((url, json.loads(data), headers))
        return answer

    monkeypatch.setattr(cybersource.requests, "post", post)
    return calls


def test_the_capture_context_is_for_the_amount_and_the_site(monkeypatch):
    from app.services import cybersource

    calls = _fake_post(monkeypatch, _Answer(201, text="eyJ.capture.context"))
    monkeypatch.setattr(cybersource, "CYBERSOURCE_TARGET_ORIGINS", ["https://everbook-album.com"])
    assert cybersource.capture_context(5800, "fr") == "eyJ.capture.context"
    url, payload, _ = calls[0]
    assert url.endswith("/up/v1/capture-contexts")
    assert payload["orderInformation"]["amountDetails"] == {"totalAmount": "58.00", "currency": "USD"}
    assert payload["targetOrigins"] == ["https://everbook-album.com"] and payload["locale"] == "fr_FR"
    assert payload["allowedPaymentTypes"] == ["PANENTRY"]


def test_a_payment_is_approved_only_when_authorized_for_the_whole_amount(monkeypatch):
    from app.services import cybersource

    ok = {"id": "7001", "status": "AUTHORIZED", "orderInformation": {"amountDetails": {"authorizedAmount": "58.00"}}}
    calls = _fake_post(monkeypatch, _Answer(201, ok))
    result = cybersource.authorize_and_capture("tok", 5800, "pay-1", {"firstName": "Rita", "email": "", "country": "LB"})
    assert result["approved"] and result["id"] == "7001"
    payload = calls[0][1]
    assert payload["tokenInformation"] == {"transientTokenJwt": "tok"}
    assert payload["processingInformation"] == {"capture": True}
    assert payload["clientReferenceInformation"] == {"code": "pay-1"}
    assert payload["orderInformation"]["billTo"] == {"firstName": "Rita", "country": "LB"}  # empty fields left out

    _fake_post(monkeypatch, _Answer(201, {**ok, "orderInformation": {"amountDetails": {"authorizedAmount": "20.00"}}}))
    assert not cybersource.authorize_and_capture("tok", 5800, "pay-1", {})["approved"]  # partly authorized
    _fake_post(monkeypatch, _Answer(201, {"id": "7002", "status": "DECLINED", "errorInformation": {"reason": "INSUFFICIENT_FUND"}}))
    declined = cybersource.authorize_and_capture("tok", 5800, "pay-1", {})
    assert not declined["approved"] and declined["reason"] == "INSUFFICIENT_FUND"
    _fake_post(monkeypatch, _Answer(502, {"status": "SERVER_ERROR"}))
    with pytest.raises(cybersource.GatewayError) as err:
        cybersource.authorize_and_capture("tok", 5800, "pay-1", {})
    assert err.value.sent  # maybe charged: checked by hand


# ---------- Paying the cart by card ----------

def test_a_printed_album_paid_by_card(client, db, shop, online_payment, monkeypatch):
    from app.services import email
    from app.services.wakilni import delivery_payload

    team_emails = []
    monkeypatch.setattr(email, "send_email", lambda to, subject, body, **k: team_emails.append(body))
    monkeypatch.setattr(email, "ORDERS_EMAIL", "orders@example.com")
    a = shop["album"]("Byblos")
    _add(client, shop, a)
    session = _session(client, shop).json()
    assert session["amount_cents"] == PRINT_24 + SHIPPING_PRICE_CENTS and session["capture_context"]
    res = _pay(client, shop, session["payment_id"])
    assert res.status_code == 200, res.text
    (order,) = res.json()["orders"]
    # Charged once, for the server's amount, with the delivery name.
    (charge,) = online_payment["charges"]
    assert charge["amount_cents"] == PRINT_24 + SHIPPING_PRICE_CENTS and charge["reference"] == session["payment_id"]
    assert charge["bill_to"]["country"] == "LB" and charge["bill_to"]["firstName"]
    assert order["payment"]["method"] == "card" and order["payment"]["reference"] == "tx-1"
    assert "paid" in [h["status"] for h in order["status_history"]]
    assert _payment(db, session["payment_id"])["status"] == "paid"
    # The courier collects nothing; the team knows it was paid by card.
    assert delivery_payload(order, {})["collection_amount"] == 0
    team = next(body for body in team_emails if "Paid by card" in body)
    assert "To collect in cash by the courier: 0.00 USD" in team


def test_a_declined_card_orders_nothing(client, db, shop, online_payment, team):
    a = shop["album"]("Byblos")
    _add(client, shop, a, "digital")
    session = _session(client, shop).json()
    online_payment["answer"] = {"approved": False, "status": "DECLINED", "id": "tx-9", "message": "", "reason": "", "raw": {}}
    res = _pay(client, shop, session["payment_id"])
    assert res.status_code == 402 and "declined" in res.json()["detail"]
    assert asyncio.run(db.orders.find_one({"album_id": a})) is None
    assert client.get("/api/cart", headers=shop["headers"]).json()["count"] == 1
    assert _payment(db, session["payment_id"])["status"] == "failed" and team == []
    # The same payment can't be tried again; a new one can.
    assert _pay(client, shop, session["payment_id"]).status_code == 400
    online_payment["answer"] = None
    assert pay_by_card(client, shop["headers"], BODY).status_code == 200


def test_a_cart_changed_after_the_card_form_opened_isnt_charged(client, db, shop, online_payment):
    a, b = shop["album"]("Byblos"), shop["album"]("Tyre")
    _add(client, shop, a)
    session = _session(client, shop).json()
    _add(client, shop, b)  # added in another tab meanwhile
    res = _pay(client, shop, session["payment_id"])
    assert res.status_code == 409 and online_payment["charges"] == []
    assert _payment(db, session["payment_id"])["status"] == "open"


def test_one_payment_is_charged_once(client, db, shop, online_payment):
    a = shop["album"]("Byblos")
    _add(client, shop, a)
    session = _session(client, shop).json()
    assert _pay(client, shop, session["payment_id"]).status_code == 200
    _add(client, shop, shop["album"]("Tyre"))
    assert _pay(client, shop, session["payment_id"]).status_code == 409
    assert len(online_payment["charges"]) == 1


def test_an_old_or_someone_elses_payment_is_refused(client, db, shop, online_payment):
    from tests.test_api import _signup

    a = shop["album"]("Byblos")
    _add(client, shop, a)
    session = _session(client, shop).json()
    _, other = _signup(client, db=db)
    res = client.post("/api/cart/checkout", json={**BODY, "payment_method": "card", "payment_id": session["payment_id"],
                                                  "transient_token": "t"}, headers=other)
    assert res.status_code == 400  # (their cart is empty, or the payment isn't theirs)
    old = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    asyncio.run(db.payments.update_one({"id": session["payment_id"]}, {"$set": {"expires_at": old}}))
    assert _pay(client, shop, session["payment_id"]).status_code == 400
    assert online_payment["charges"] == []


def test_no_answer_from_cybersource_orders_nothing_and_tells_the_team(client, db, shop, online_payment, team):
    from app.services.cybersource import GatewayError

    a = shop["album"]("Byblos")
    _add(client, shop, a)
    session = _session(client, shop).json()
    online_payment["error"] = GatewayError("timed out", sent=True)
    res = _pay(client, shop, session["payment_id"])
    assert res.status_code == 502 and "don't pay again" in res.json()["detail"]
    assert _payment(db, session["payment_id"])["status"] == "unknown" and len(team) == 1
    assert asyncio.run(db.orders.find_one({"album_id": a})) is None


def test_cash_on_delivery_stays_for_printed_albums_only(client, db, shop, online_payment):
    a = shop["album"]("Byblos")
    _add(client, shop, a)
    cart = client.get("/api/cart", headers=shop["headers"]).json()
    assert cart["card_payment"] is True and cart["pay_now_cents"] == 0
    res = client.post("/api/cart/checkout", json=BODY, headers=shop["headers"])
    assert res.status_code == 200
    (order,) = res.json()["orders"]
    assert "payment" not in order and "paid" not in [h["status"] for h in order["status_history"]]
    # A PDF in the cart: paid by card, not cash.
    _add(client, shop, shop["album"]("Tyre"), "digital")
    cart = client.get("/api/cart", headers=shop["headers"]).json()
    assert cart["pay_now_cents"] == DIGITAL_PRICE_CENTS
    assert client.post("/api/cart/checkout", json=BODY, headers=shop["headers"]).status_code == 400
    assert online_payment["charges"] == []


def test_no_card_form_without_card_payment(client, shop):
    a = shop["album"]("Byblos")
    _add(client, shop, a)
    assert _session(client, shop).status_code == 400
    assert client.get("/api/cart", headers=shop["headers"]).json()["card_payment"] is False
