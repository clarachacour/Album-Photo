"""A customer's albums ordered together: one printer email, one "ready"
click, one Wakilni delivery, the delivery paid once."""
import asyncio
from datetime import datetime, timedelta, timezone

from app.core.signed_links import sign_order_action
from app.services.pricing import SHIPPING_PRICE_CENTS, TERMS_VERSION
from tests.test_api import _signup
from tests.test_wakilni import ADDRESS, _order, _ready, courier  # noqa: F401  (fixture)


def _second_order(client, db, headers, title="Batroun", address=ADDRESS):
    album_id = client.post("/api/albums", json={"title": title, "size": "A4", "target_pages": 24}, headers=headers).json()["id"]
    asyncio.run(db.albums.update_one({"id": album_id}, {"$set": {"pages": [{"id": "1", "items": []}], "status": "ready"}}))
    body = {"album_id": album_id, "shipping_address": address, "accepted_terms_version": TERMS_VERSION}
    return client.post("/api/orders", json=body, headers=headers).json()


def _wait_over(db, *order_ids):
    long_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    asyncio.run(db.orders.update_many({"id": {"$in": list(order_ids)}}, {"$set": {"printer_pending_at": long_ago}}))


def test_albums_ordered_together_go_to_the_printer_and_the_courier_together(client, db, courier):  # noqa: F811
    from app.services.print_groups import flush_printer_queue

    asyncio.run(db.orders.update_many({"id": {"$ne": courier["order"]["id"]}, "printer_pending_at": {"$exists": True}}, {"$unset": {"printer_pending_at": ""}}))
    first = courier["order"]
    second = _second_order(client, db, courier["customer"])
    # Someone else's order, same time: its own email.
    _, other = _signup(client, db=db)
    elsewhere = _second_order(client, db, other, "Tyre", {**ADDRESS, "phone": "+961 70 000 000"})
    sent = courier["sent"]

    # Within the hour: nothing yet.
    assert asyncio.run(flush_printer_queue()) == 0 and not sent.get("printer")
    _wait_over(db, first["id"], second["id"], elsewhere["id"])
    assert asyncio.run(flush_printer_queue()) == 2
    assert sorted(sent["printer"]) == sorted([[first["id"], second["id"]], [elsewhere["id"]]])
    assert asyncio.run(flush_printer_queue()) == 0  # sent once

    # The delivery is paid once: by the first order of the group.
    lead, other_album = _order(db, first["id"]), _order(db, second["id"])
    assert lead["shipping_price_cents"] == SHIPPING_PRICE_CENTS
    assert other_album["shipping_price_cents"] == 0 and other_album["shipping_waived_cents"] == SHIPPING_PRICE_CENTS
    assert other_album["total_price_cents"] == second["total_price_cents"] - SHIPPING_PRICE_CENTS

    # The printer's page lists both albums, each with its PDF.
    info = client.get(f"/api/order-actions/{first['id']}/info", params={"token": sign_order_action(first["id"], "ready")}).json()
    assert [a["order_id"] for a in info["albums"]] == [first["id"], second["id"]]

    # One click: both ready, one Wakilni delivery with both albums.
    assert _ready(client, first["id"]).status_code == 200
    adds = [body for _, path, body in courier["fake"].calls if "/add_delivery/" in path]
    assert len(adds) == 1
    sent_delivery = adds[0]
    assert [p["sku"] for p in sent_delivery["packages"]] == [f"EB-{first['id'][:8].upper()}", f"EB-{second['id'][:8].upper()}"]
    assert sent_delivery["waybill"] == f"EB-{first['id'][:8].upper()}"
    assert sent_delivery["collection_amount"] == (lead["total_price_cents"] + other_album["total_price_cents"]) / 100
    for oid in (first["id"], second["id"]):
        order = _order(db, oid)
        assert order["status"] == "ready_for_delivery" and order["delivery"]["delivery_id"] == courier["fake"].delivery_id
    assert _order(db, elsewhere["id"])["status"] == "printing"  # not part of it

    # Cancelling the delivery cancels it for both albums.
    from app.services.delivery import cancel_delivery

    asyncio.run(cancel_delivery(second["id"], "test"))
    assert all(_order(db, oid)["delivery"].get("cancelled") for oid in (first["id"], second["id"]))


def test_the_admin_can_send_a_waiting_order_to_the_printer_at_once(client, db, courier, monkeypatch):  # noqa: F811
    from app.core import auth

    order_id = courier["order"]["id"]
    assert _order(db, order_id).get("printer_pending_at")
    email, admin = _signup(client, db=db)
    monkeypatch.setattr(auth, "ADMIN_EMAIL", email)
    assert client.post(f"/api/admin/orders/{order_id}/resend-printer-email", headers=admin).json() == {"sent": True}
    assert [order_id] in courier["sent"]["printer"]
    assert not _order(db, order_id).get("printer_pending_at")


def test_the_package_still_goes_if_the_first_order_is_cancelled(client, db, courier):  # noqa: F811
    from app.services.print_groups import flush_printer_queue

    first = courier["order"]
    second = _second_order(client, db, courier["customer"])
    asyncio.run(flush_printer_queue(force_order_id=first["id"]))
    asyncio.run(db.orders.update_one({"id": first["id"]}, {"$set": {"status": "cancelled"}}))
    token = {"token": sign_order_action(first["id"], "ready")}
    info = client.get(f"/api/order-actions/{first['id']}/info", params=token).json()
    assert not info["cancelled"] and not info["ready"]
    assert _ready(client, first["id"]).status_code == 200
    assert _order(db, second["id"])["status"] == "ready_for_delivery"
    assert _order(db, first["id"])["status"] == "cancelled"
    adds = [body for _, path, body in courier["fake"].calls if "/add_delivery/" in path]
    # The number written on the package stays the group's.
    assert len(adds) == 1 and adds[0]["waybill"] == f"EB-{first['id'][:8].upper()}"
    assert [p["sku"] for p in adds[0]["packages"]] == [f"EB-{second['id'][:8].upper()}"]


def test_the_customer_gets_one_shipped_and_one_delivered_email_for_the_package(client, db, courier):  # noqa: F811
    from app.services.delivery import sync_all_deliveries
    from app.services.print_groups import flush_printer_queue

    first = courier["order"]
    second = _second_order(client, db, courier["customer"])
    asyncio.run(flush_printer_queue(force_order_id=first["id"]))
    _ready(client, first["id"])
    sent, fake = courier["sent"], courier["fake"]
    fake.status_logs = [{"status": "Processing", "status_code": 3, "created_at": "2026-10-20 10:00:00"}]
    package = [first["id"], second["id"]]
    mine = lambda groups: [g for g in groups if set(g) & set(package)]  # noqa: E731 (other tests' deliveries too)
    asyncio.run(sync_all_deliveries())
    assert mine(sent["shipped_groups"]) == [package]
    assert all(_order(db, oid)["status"] == "shipped" for oid in package)
    asyncio.run(sync_all_deliveries())  # nothing new: no second email
    assert len(mine(sent["shipped_groups"])) == 1
    fake.status_logs.insert(0, {"status": "Success", "status_code": 4, "created_at": "2026-10-20 15:00:00"})
    asyncio.run(sync_all_deliveries())
    assert mine(sent["delivered_groups"]) == [package]
    assert all(_order(db, oid)["status"] == "delivered" for oid in package)
    # Wakilni was asked once per round for the package, not once per album.
    from app.services.delivery import sync_delivery

    before = len([p for _, p, _ in fake.calls if p.endswith("/orders/status")])
    asyncio.run(db.orders.update_many({"id": {"$in": package}}, {"$set": {"status": "shipped"}}))
    asyncio.run(sync_delivery(first["id"]))
    assert len([p for _, p, _ in fake.calls if p.endswith("/orders/status")]) == before + 1


def test_bookstop_gets_a_whatsapp_for_each_order_to_print(client, db, courier, monkeypatch):  # noqa: F811
    from app.core.order_number import order_number
    from app.services import whatsapp
    from app.services.print_groups import flush_printer_queue

    posted = []
    monkeypatch.setattr(whatsapp, "WHATSAPP_TOKEN", "wa-token")
    monkeypatch.setattr(whatsapp, "WHATSAPP_PHONE_NUMBER_ID", "123")
    monkeypatch.setattr(whatsapp, "WHATSAPP_PRINTER_TO", ["+961 1 222 333"])
    monkeypatch.setattr(whatsapp, "WHATSAPP_PICKUP_TO", [])
    monkeypatch.setattr(whatsapp.requests, "post", lambda url, json=None, headers=None, timeout=None: (posted.append(json), type("R", (), {"status_code": 200})())[1])

    asyncio.run(db.orders.update_many({"id": {"$ne": courier["order"]["id"]}, "printer_pending_at": {"$exists": True}}, {"$unset": {"printer_pending_at": ""}}))
    first = courier["order"]
    second = _second_order(client, db, courier["customer"])
    _wait_over(db, first["id"], second["id"])
    asyncio.run(flush_printer_queue())
    # One message for the two albums printed together, still with the email.
    assert len(posted) == 1 and posted[0]["to"] == "9611222333"
    assert posted[0]["template"]["name"] == "bookstop_new_order"
    params = [p["text"] for p in posted[0]["template"]["components"][0]["parameters"]]
    numbers = {order_number(_order(db, first["id"])), order_number(_order(db, second["id"]))}
    assert set(params[0].split(", ")) == numbers and params[1] == "2"
    assert len(courier["sent"]["printer"]) == 1


def test_an_order_cancelled_while_its_pdf_is_made_never_goes_to_the_printer(client, db, courier):  # noqa: F811
    from app.services.orders import generate_order_pdf
    from app.services.print_groups import flush_printer_queue

    order = courier["order"]
    # Cancelled by the admin before its PDF was finished.
    asyncio.run(db.orders.update_one({"id": order["id"]}, {"$set": {"status": "cancelled", "pdf_ready": False}, "$unset": {"printer_pending_at": ""}}))
    assert asyncio.run(generate_order_pdf(order["id"], order["album_id"], _order(db, order["id"])["user_id"]))
    after = _order(db, order["id"])
    assert after["status"] == "cancelled" and not after.get("printer_pending_at")
    _wait_over(db, order["id"])
    asyncio.run(flush_printer_queue())
    assert not any(order["id"] in g for g in courier["sent"].get("printer", []))
