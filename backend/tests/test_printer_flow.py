def _order(**extra):
    return {
        "id": "5f4c0509-1111-2222-3333-444455556666",
        "user_id": "u1",
        "album_title": "Sicily",
        "size": "A4",
        "orientation": "portrait",
        "quantity": 2,
        "total_price_cents": 13400,
        "unit_price_cents": 6700,
        "currency": "USD",
        "status": "printing",
        "shipping_address": {"full_name": "Rita Haddad", "phone": "70123456", "street": "Rue Sioufi", "city": "Beirut"},
        **extra,
    }


def _capture(monkeypatch, email_module):
    sent = []
    monkeypatch.setattr(email_module, "send_email", lambda to, subject, body, html_body=None, reply_to=None: sent.append((to, subject, body, html_body or "")))
    return sent


def test_the_printer_gets_the_order_number_and_never_the_price(app, monkeypatch):
    from app.services import email as email_module

    monkeypatch.setattr(email_module, "PRINTER_EMAIL", "print@shop.test")
    sent = _capture(monkeypatch, email_module)
    email_module.send_printer_order_email(_order())
    (to, subject, body, html), = sent
    assert to == "print@shop.test"
    for text in (subject, body, html):
        assert "EB-5F4C0509" in text
        assert "134" not in text and "67" not in text and "$" not in text


def test_the_courier_email_has_the_order_number_and_no_price(app, monkeypatch):
    from app.services import email as email_module

    monkeypatch.setattr(email_module, "DELIVERY_EMAIL", "courier@test")
    sent = _capture(monkeypatch, email_module)
    email_module.send_delivery_pickup_email(_order())
    (_, subject, body, html), = sent
    assert "EB-5F4C0509" in body and "EB-5F4C0509" in html
    assert "134" not in body and "$" not in body


def test_the_customer_hears_the_book_is_being_printed(app, monkeypatch):
    from app.services import email as email_module

    sent = _capture(monkeypatch, email_module)
    email_module.send_order_in_production_email("rita@example.com", "Rita", _order())
    (to, subject, body, _), = sent
    assert to == "rita@example.com" and "EB-5F4C0509" in subject and "printer" in body


def test_wakilni_waybill_is_the_same_order_number(app):
    from app.services import wakilni

    assert wakilni.waybill(_order()) == "EB-5F4C0509"
