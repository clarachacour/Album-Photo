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


def test_albums_ordered_together_come_in_one_printer_email(app, monkeypatch):
    from app.services import email as email_module

    monkeypatch.setattr(email_module, "PRINTER_EMAIL", "print@shop.test")
    sent = _capture(monkeypatch, email_module)
    second = _order(id="6a1b0000-1111-2222-3333-444455556666", album_title="Batroun", quantity=1)
    email_module.send_printer_order_email(_order(), [_order(), second])
    (to, subject, body, html), = sent
    assert "2 albums, one package (EB-5F4C0509)" in subject
    # Both albums, each with its PDF; one ready link (the lead's), for both.
    assert "EB-6A1B0000" in body and "Batroun" in html and "all 3 books in one package" in body
    assert body.count("/printer/5f4c0509-1111-2222-3333-444455556666/download") == 1
    assert body.count("/printer/6a1b0000-1111-2222-3333-444455556666/download") == 1
    assert "/printer/6a1b0000-1111-2222-3333-444455556666?" not in body
    assert "$" not in body and "134" not in body


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


def test_the_printer_links_use_the_site_address_not_the_server(app, monkeypatch):
    from app.services import email as email_module

    monkeypatch.setattr(email_module, "PRINTER_EMAIL", "print@shop.test")
    monkeypatch.setattr(email_module, "FRONTEND_URL", "https://everbook-album.com")
    sent = _capture(monkeypatch, email_module)
    email_module.send_printer_order_email(_order())
    (_, _, body, html), = sent
    for text in (body, html):
        assert "https://everbook-album.com/printer/5f4c0509-1111-2222-3333-444455556666/download?token=" in text
        assert "https://everbook-album.com/printer/5f4c0509-1111-2222-3333-444455556666?token=" in text
        assert "run.app" not in text and "/api/" not in text


def test_opening_the_ready_link_does_not_mark_the_book_ready(client, db):
    """Mail scanners open every link: only the button on the page counts."""
    import asyncio
    from app.core.signed_links import sign_order_action

    oid = "5f4c0509-1111-2222-3333-444455556666"
    asyncio.run(db.orders.insert_one(_order()))
    token = sign_order_action(oid, "ready")
    r = client.get(f"/api/order-actions/{oid}/ready?token={token}", follow_redirects=False)
    assert r.status_code in (302, 307) and f"/printer/{oid}?token={token}" in r.headers["location"]
    assert asyncio.run(db.orders.find_one({"id": oid}))["status"] == "printing"

    info = client.get(f"/api/order-actions/{oid}/info?token={token}").json()
    assert info["order_number"] == "EB-5F4C0509" and info["ready"] is False
    assert "price" not in str(info) and "Rita" not in str(info)
    assert client.get(f"/api/order-actions/{oid}/info?token=wrong").status_code == 403
    assert client.post(f"/api/order-actions/{oid}/ready?token=wrong").status_code == 403


def test_one_shipped_and_one_delivered_email_for_albums_delivered_together(app, monkeypatch):
    from app.services import email as email_module

    sent = _capture(monkeypatch, email_module)
    second = _order(id="6a1b0000-1111-2222-3333-444455556666", album_title="Batroun")
    group = [_order(delivery={"tracking_url": "https://track.wakilni.com/WK1"}), second]
    email_module.send_order_shipped_email("rita@example.com", "Rita", group[0], group)
    email_module.send_order_delivered_feedback_email("rita@example.com", "Rita", group[0], group)
    (shipped_subject, shipped, _), (delivered_subject, delivered, _) = [(s, b, h) for _, s, b, h in sent]
    assert "2 Everbook albums are on their way" in shipped_subject
    assert "Sicily (EB-5F4C0509)" in shipped and "Batroun (EB-6A1B0000)" in shipped and "https://track.wakilni.com/WK1" in shipped
    assert "turn out" in delivered_subject
    assert "/orders/5f4c0509-1111-2222-3333-444455556666/feedback" in delivered and "/orders/6a1b0000-1111-2222-3333-444455556666/feedback" in delivered
