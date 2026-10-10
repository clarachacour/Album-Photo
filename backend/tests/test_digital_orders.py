"""The digital album: the PDF to download, priced at the printed album's
price minus DIGITAL_DISCOUNT_CENTS, made at once but handed over only once
the payment is confirmed in the admin."""
import asyncio

import pytest

from app.services.pricing import DIGITAL_DISCOUNT_CENTS, SHIPPING_PRICE_CENTS, TERMS_VERSION, compute_order_price_cents
from tests.test_api import _signup

ADDRESS = {"full_name": "A", "phone": "1", "street": "S", "city": "C"}


@pytest.fixture()
def shop(client, db, monkeypatch):
    from app.core import auth
    from app.routers import orders as orders_router
    from app.services import orders

    sent = {"ready": [], "printer": [], "confirmation": [], "renders": []}

    def render(url, pages, label):
        sent["renders"].append(url)
        return b"%PDF-1.4 album"

    monkeypatch.setattr(orders, "pdf_tasks_enabled", lambda: False)
    monkeypatch.setattr(orders, "render_album_pdf_sync", render)
    monkeypatch.setattr(orders, "put_object", lambda *a, **k: {"path": a[0]})
    monkeypatch.setattr(orders, "delete_object", lambda *a, **k: None)
    monkeypatch.setattr(orders, "send_printer_order_email", lambda order: sent["printer"].append(order["id"]))
    monkeypatch.setattr(orders, "send_digital_album_ready_email", lambda to, name, order: sent["ready"].append(order["id"]))
    monkeypatch.setattr(orders_router, "send_order_confirmation_email", lambda to, name, order: sent["confirmation"].append(order.get("kind")))
    monkeypatch.setattr(orders_router, "get_r2_client", lambda: type("R2", (), {"generate_presigned_url": lambda self, *a, **k: "https://r2/album.pdf"})())

    admin_email, admin = _signup(client, db=db)
    monkeypatch.setattr(auth, "ADMIN_EMAIL", admin_email)
    _, customer = _signup(client, db=db)
    album_id = client.post("/api/albums", json={"title": "Été à Byblos", "size": "A4", "target_pages": 24}, headers=customer).json()["id"]
    pages = [{"id": str(i), "items": []} for i in range(24)]
    asyncio.run(db.albums.update_one({"id": album_id}, {"$set": {"pages": pages, "status": "ready"}}))
    return {"admin": admin, "customer": customer, "album_id": album_id, "sent": sent}


def _order(client, shop, kind, **extra):
    body = {"album_id": shop["album_id"], "kind": kind, "accepted_terms_version": TERMS_VERSION, **extra}
    return client.post("/api/orders", json=body, headers=shop["customer"])


def test_a_digital_album_is_handed_over_once_paid(client, db, shop):
    res = _order(client, shop, "digital")
    assert res.status_code == 200, res.text
    order = res.json()
    assert order["kind"] == "digital" and order["shipping_address"] is None
    assert order["total_price_cents"] == compute_order_price_cents("A4", 24) - DIGITAL_DISCOUNT_CENTS
    assert order["shipping_price_cents"] == 0 and order["quantity"] == 1
    assert shop["sent"]["confirmation"] == ["digital"]

    # Made at once, in the reader's version, never sent to the printer…
    assert "digital=1" in shop["sent"]["renders"][0]
    assert order["pdf_ready"] and order["status"] == "pending_payment"
    assert shop["sent"]["printer"] == [] and shop["sent"]["ready"] == []
    # …and not downloadable before the payment is confirmed.
    url = f"/api/orders/{order['id']}/download"
    assert client.get(url, headers=shop["customer"]).status_code == 403
    detail = client.get(f"/api/orders/{order['id']}", headers=shop["customer"]).json()
    assert [s["status"] for s in detail["timeline"]] == ["pending_payment", "paid", "available"]

    # The admin can't move it to a printed book's status.
    status_url = f"/api/admin/orders/{order['id']}/status"
    assert client.patch(status_url, json={"status": "printing"}, headers=shop["admin"]).status_code == 400
    # Paid: the customer gets the email, once, and the download.
    paid = client.patch(status_url, json={"status": "paid"}, headers=shop["admin"]).json()
    assert paid["status"] == "available"
    client.patch(status_url, json={"status": "available"}, headers=shop["admin"])
    assert shop["sent"]["ready"] == [order["id"]]
    assert client.get(url, headers=shop["customer"]).json() == {"url": "https://r2/album.pdf"}


def test_the_printed_book_after_the_digital_album_costs_the_difference(client, shop):
    digital = _order(client, shop, "digital").json()
    assert _order(client, shop, "digital").status_code == 409  # one of each kind
    assert _order(client, shop, "print").status_code == 400  # a printed book needs an address

    printed = _order(client, shop, "print", shipping_address=ADDRESS).json()
    assert printed["kind"] == "print" and printed["credit_cents"] == digital["total_price_cents"]
    assert printed["total_price_cents"] == compute_order_price_cents("A4", 24) + SHIPPING_PRICE_CENTS - digital["total_price_cents"]
    assert shop["sent"]["printer"] == [printed["id"]]
    assert "digital=1" not in shop["sent"]["renders"][-1]
