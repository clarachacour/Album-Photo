import pytest

pytestmark = pytest.mark.free_trial


@pytest.fixture(autouse=True)
def trial_on(app, monkeypatch):
    from app.services import pricing

    monkeypatch.setattr(pricing, "FREE_TRIAL", True)


def test_albums_are_free_and_only_delivery_is_due(app):
    from app.services.pricing import SHIPPING_PRICE_CENTS, compute_digital_price_cents, compute_order_price_cents

    assert compute_order_price_cents("A4", 200) == 0
    assert compute_digital_price_cents("A5", 24) == 0
    assert SHIPPING_PRICE_CENTS == 500


def test_the_confirmation_email_says_only_delivery_is_paid_in_cash(app, monkeypatch):
    from app.services import email as email_module

    sent = []
    monkeypatch.setattr(email_module, "send_email", lambda to, subject, body, html_body=None, reply_to=None: sent.append(body))
    order = {"id": "abc12345-x", "kind": "print", "unit_price_cents": 0, "total_price_cents": 500, "currency": "usd", "quantity": 1}
    email_module.send_order_confirmation_email("rita@example.com", "Rita", order)
    assert "free" in sent[0] and "5.00 USD" in sent[0] and "cash to the courier" in sent[0]


def test_wakilni_collects_only_the_delivery_even_for_an_order_placed_before(app):
    from app.services import wakilni

    old_order = {
        "id": "5f4c0509-aaaa", "user_id": "u1", "status": "printing", "quantity": 1, "size": "A4",
        "unit_price_cents": 3500, "shipping_price_cents": 500, "total_price_cents": 4000,
        "shipping_address": {"full_name": "Rita Haddad", "phone": "70123456", "street": "Rue Sioufi", "city": "Beirut"},
    }
    payload = wakilni.delivery_payload(old_order, {"email": "rita@example.com"})
    assert payload["collection_amount"] == 5.0
    assert payload["cash_collection_type_id"] == wakilni.COLLECTION_ON_DELIVERY
    assert payload["waybill"] == "EB-5F4C0509"
