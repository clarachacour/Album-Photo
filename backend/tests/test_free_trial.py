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
