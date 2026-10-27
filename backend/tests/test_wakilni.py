"""Wakilni deliveries: created when the printer marks a book ready,
followed until delivered, with a fake Wakilni answering as documented."""
import asyncio
import itertools

import pytest

from app.core.signed_links import sign_order_action
from app.services.pricing import TERMS_VERSION
from tests.test_api import _signup

ADDRESS = {"full_name": "Rita Khoury Haddad", "phone": "+961 3 123 456", "street": "Rue Hamra", "building": "Bldg 5",
           "city": "Beirut", "area": "Hamra", "additional_info": "3rd floor"}


_delivery_numbers = itertools.count()


class FakeWakilni:
    """Answers like Wakilni's API and records what it was sent."""

    def __init__(self):
        self.calls = []
        self.status_logs = []
        self.comments = []
        self.fail_add = False
        self.down = False
        self.fail_cancel = False
        # Its own delivery number for each test: the test database is
        # shared, and albums with the same delivery are followed together.
        self.delivery_id = 9001 + next(_delivery_numbers)

    def request(self, method, url, json=None, params=None, headers=None, timeout=None):
        path = url.split("wakilni.test", 1)[1]
        self.calls.append((method, path, json))
        if self.down:  # their database overloaded, as seen in production
            return _Res(500, {"message": "SQLSTATE[HY000] [1040] Too many connections", "code": 1040, "status_code": 500})
        if path.endswith("/auth_token"):
            return _Res(200, {"message": "Auth token retrieved successfully", "token": "tok"})
        if path.endswith("/start_bulk"):
            return _Res(200, {"message": "Bulk order opened", "bulk_id": 77})
        if "/add_delivery/" in path:
            if self.fail_add:
                return _Res(422, {"message": "The receiver area is invalid"})
            if "waybill" not in (json or {}):
                return _Res(422, {"message": "Could not add delivery order.", "errors": {"waybill": ["The waybill field is required."]}})
            if not isinstance(json["waybill"], str):
                return _Res(422, {"message": "Could not add delivery order.", "errors": {"waybill": ["The waybill must be a string."]}})
            return _Res(200, {"message": "Delivery order added", "delivery_id": self.delivery_id, "tracking_id": "WK123",
                              "tracking_url": "https://track.wakilni.com/WK123", "packages": []})
        if "/end_bulk/" in path:
            return _Res(200, {"message": "Closed Bulk order", "bulk_id": 77})
        if path.endswith("/orders/status"):
            return _Res(200, {"success": True, "data": {"tracking_id": "WK123", "comments": self.comments, "logs": self.status_logs}})
        if path.endswith("/cancel") and self.fail_cancel:
            return _Res(422, {"message": "Order can't be canceled"})
        if path.endswith("/cancel"):
            return _Res(200, {"message": "Order canceled", "delivery_id": self.delivery_id})
        return _Res(404, {"message": "unknown"})

    def get(self, url, params=None, timeout=None):
        return self.request("GET", url, params=params)


class _Res:
    def __init__(self, status_code, body):
        self.status_code, self._body, self.text = status_code, body, str(body)

    def json(self):
        return self._body


@pytest.fixture()
def courier(client, db, monkeypatch):
    from app.routers import orders as orders_router
    from app.services import delivery, orders, wakilni

    fake = FakeWakilni()
    monkeypatch.setattr(wakilni, "WAKILNI_URL", "https://api.wakilni.test")
    monkeypatch.setattr(wakilni, "WAKILNI_KEY", "key")
    monkeypatch.setattr(wakilni, "WAKILNI_SECRET", "secret")
    wakilni._token.update(value=None, at=0)
    monkeypatch.setattr(wakilni.requests, "request", fake.request)
    monkeypatch.setattr(wakilni.requests, "get", fake.get)

    sent = {"courier": [], "problem": [], "shipped": [], "delivered": []}
    monkeypatch.setattr(delivery, "send_delivery_pickup_email", lambda order, group=None: sent["courier"].append(order["id"]))
    monkeypatch.setattr(delivery, "send_delivery_problem_email", lambda order, problem: sent["problem"].append(problem))
    monkeypatch.setattr(delivery, "send_order_shipped_email", lambda to, name, order, group=None: (sent["shipped"].append(order["delivery"]["tracking_url"]), sent.setdefault("shipped_groups", []).append([o["id"] for o in group or [order]])))
    monkeypatch.setattr(delivery, "send_order_delivered_feedback_email", lambda to, name, order, group=None: (sent["delivered"].append(order["id"]), sent.setdefault("delivered_groups", []).append([o["id"] for o in group or [order]])))
    monkeypatch.setattr(orders, "pdf_tasks_enabled", lambda: False)
    monkeypatch.setattr(orders, "render_album_pdf_sync", lambda *a: b"%PDF")
    monkeypatch.setattr(orders, "put_object", lambda *a, **k: {"path": a[0]})
    monkeypatch.setattr(orders, "delete_object", lambda *a, **k: None)
    from app.services import print_groups

    monkeypatch.setattr(print_groups, "send_printer_order_email", lambda order, group=None: sent.setdefault("printer", []).append([o["id"] for o in (group or [order])]))
    monkeypatch.setattr(orders_router, "send_order_confirmation_email", lambda *a: None)

    _, customer = _signup(client, db=db)
    album_id = client.post("/api/albums", json={"title": "Byblos", "size": "A5", "target_pages": 24}, headers=customer).json()["id"]
    asyncio.run(db.albums.update_one({"id": album_id}, {"$set": {"pages": [{"id": "1", "items": []}], "status": "ready"}}))
    order = client.post("/api/orders", json={"album_id": album_id, "shipping_address": ADDRESS, "accepted_terms_version": TERMS_VERSION}, headers=customer).json()
    return {"fake": fake, "sent": sent, "order": order, "customer": customer}


def _ready(client, order_id):
    return client.post(f"/api/order-actions/{order_id}/ready", params={"token": sign_order_action(order_id, "ready")})


def _order(db, order_id):
    return asyncio.run(db.orders.find_one({"id": order_id}, {"_id": 0}))


def test_the_printers_click_creates_the_wakilni_delivery(client, db, courier):
    order_id = courier["order"]["id"]
    assert _ready(client, order_id).status_code == 200
    paths = [p for _, p, _ in courier["fake"].calls]
    assert paths == ["/api/v2/third_party/auth_token", "/api/v2/clients/start_bulk", "/api/v2/clients/add_delivery/77", "/api/v2/clients/end_bulk/77"]
    pickup = courier["fake"].calls[1][2]
    assert pickup["area"] == "Furn el-Chebbak"
    sent = courier["fake"].calls[2][2]
    assert (sent["receiver_first_name"], sent["receiver_last_name"]) == ("Rita", "Khoury Haddad")
    assert sent["receiver_area"] == "Hamra" and sent["is_express"] is False
    assert sent["waybill"] == f"EB-{order_id[:8].upper()}"  # required by Wakilni, as text
    # Not paid yet: the courier collects the total in cash.
    assert sent["cash_collection_type_id"] == 52 and sent["collection_amount"] == courier["order"]["total_price_cents"] / 100
    assert sent["packages"][0]["type_id"] == 59  # A5: small box
    order = _order(db, order_id)
    assert order["status"] == "ready_for_delivery" and order["delivery"]["tracking_url"] == "https://track.wakilni.com/WK123"
    assert courier["sent"]["courier"] == [order_id]  # Wakilni's team is emailed too
    _ready(client, order_id)  # a second click doesn't create a second delivery
    assert sum("start_bulk" in p for _, p, _ in courier["fake"].calls) == 1
    assert courier["sent"]["courier"] == [order_id]  # nor a second email


def test_a_paid_order_has_nothing_to_collect():
    from app.services.wakilni import delivery_payload

    order = {"id": "abcdef12-0000", "user_id": "u-1", "size": "A4", "total_price_cents": 4000, "status": "printing",
             "status_history": [{"status": "paid"}], "shipping_address": ADDRESS}
    sent = delivery_payload(order, {"email": "rita@example.com"})
    assert sent["cash_collection_type_id"] == 54 and sent["collection_amount"] == 0
    assert sent["packages"][0]["type_id"] == 58  # A4: regular box


def test_the_delivery_is_followed_until_delivered(client, db, courier):
    from app.services.delivery import sync_all_deliveries, sync_delivery

    order_id = courier["order"]["id"]
    _ready(client, order_id)
    fake = courier["fake"]
    fake.status_logs = [{"status": "Processing", "status_code": 3, "created_at": "2026-10-12 10:00:00"},
                        {"status": "Confirmed", "status_code": 2, "created_at": "2026-10-12 09:00:00"}]
    # The scheduler's job follows every delivery on its way, this one included.
    assert asyncio.run(sync_all_deliveries())["checked"] >= 1
    assert _order(db, order_id)["status"] == "shipped"
    assert "https://track.wakilni.com/WK123" in courier["sent"]["shipped"]
    shipped = len(courier["sent"]["shipped"])
    asyncio.run(sync_delivery(order_id))  # nothing new: no second email
    assert len(courier["sent"]["shipped"]) == shipped

    fake.status_logs.insert(0, {"status": "Success", "status_code": 4, "created_at": "2026-10-12 12:00:00"})
    asyncio.run(sync_delivery(order_id))
    assert _order(db, order_id)["status"] == "delivered" and order_id in courier["sent"]["delivered"]


def test_problems_are_reported_to_the_admin_once(client, db, courier):
    from app.services.delivery import sync_delivery

    order_id = courier["order"]["id"]
    _ready(client, order_id)
    courier["fake"].status_logs = [{"status": "Postponed", "status_code": 9, "created_at": "2026-10-12 10:00:00"}]
    asyncio.run(sync_delivery(order_id))
    asyncio.run(sync_delivery(order_id))
    assert len(courier["sent"]["problem"]) == 1 and "postponed" in courier["sent"]["problem"][0]

    courier["fake"].status_logs = [{"status": "Success", "status_code": 4, "created_at": "2026-10-12 12:00:00"},
                                   {"status": "Success, Rejected", "status_code": 4, "created_at": "2026-10-12 12:00:00"}]
    asyncio.run(sync_delivery(order_id))
    assert "refused" in courier["sent"]["problem"][-1]
    assert _order(db, order_id)["status"] != "delivered"


def test_if_wakilni_refuses_the_courier_is_emailed_and_the_admin_told(client, db, courier):
    courier["fake"].fail_add = True
    order_id = courier["order"]["id"]
    res = _ready(client, order_id)
    order = _order(db, order_id)
    assert "receiver area" in order["delivery"]["error"]
    # No Wakilni number: ours goes on the package (Wakilni has it as the waybill).
    assert res.json()["package_number"] == f"EB-{order_id[:8].upper()}" and res.json()["package_number_from"] == "everbook"
    assert courier["sent"]["courier"] == [order_id] and len(courier["sent"]["problem"]) == 1
    assert "/api/v2/clients/end_bulk/77" in [p for _, p, _ in courier["fake"].calls]  # the empty pickup is closed


def test_outside_the_test_week_the_courier_collects_the_whole_total(app):
    from app.services import wakilni

    order = {"id": "5f4c0509-aaaa", "status": "printing", "total_price_cents": 4000, "unit_price_cents": 3500, "shipping_price_cents": 500,
             "created_at": "2026-10-20T09:00:00+00:00", "shipping_address": {}}
    assert wakilni.delivery_payload(order, {})["collection_amount"] == 40.0


def test_an_order_placed_before_the_test_week_stays_offered(app):
    from app.services import wakilni

    order = {"id": "5f4c0509-aaaa", "status": "printing", "total_price_cents": 4000, "unit_price_cents": 3500, "shipping_price_cents": 500,
             "created_at": "2026-10-10T09:00:00+00:00", "shipping_address": {}}
    assert wakilni.delivery_payload(order, {})["collection_amount"] == 5.0
    # …and so does one placed during it, at 0 for the album.
    order.update(created_at="2026-10-15T09:00:00+00:00", unit_price_cents=0, total_price_cents=500)
    assert wakilni.delivery_payload(order, {})["collection_amount"] == 5.0


def test_the_admin_sees_the_whole_delivery_history(client, db, courier, monkeypatch):
    from app.core import auth

    order_id = courier["order"]["id"]
    _ready(client, order_id)
    courier["fake"].status_logs = [
        {"status": "Processing", "status_code": 3, "created_at": "2026-10-14 10:58:49"},
        {"status": "Confirmed", "status_code": 2, "created_at": "2026-10-14 09:40:22"},
        {"status": "Success", "status_code": 4, "created_at": "2026-10-14 15:22:24"},
    ]
    courier["fake"].comments = ["Call before delivery", "No answer"]
    email, admin = _signup(client, db=db)
    monkeypatch.setattr(auth, "ADMIN_EMAIL", email)
    res = client.get(f"/api/admin/orders/{order_id}/delivery/history", headers=admin)
    assert res.status_code == 200, res.text
    body = res.json()
    assert [log["status"] for log in body["logs"]] == ["Confirmed", "Processing", "Success"]  # oldest first
    assert body["comments"] == ["Call before delivery", "No answer"] and body["tracking_id"] == "WK123"
    # Not for a customer.
    assert client.get(f"/api/admin/orders/{order_id}/delivery/history", headers=courier["customer"]).status_code == 403


def test_wakilni_down_waits_for_the_next_round_and_alerts_only_after_hours(client, db, courier, caplog):
    from datetime import datetime, timedelta, timezone

    from app.services.delivery import sync_all_deliveries

    _ready(client, courier["order"]["id"])
    asyncio.run(db.app_state.delete_many({}))
    courier["fake"].down = True
    from app.services import wakilni
    wakilni._token.update(value=None, at=0)
    calls = len(courier["fake"].calls)
    with caplog.at_level("WARNING"):
        result = asyncio.run(sync_all_deliveries())
    # Stopped at the first failure (no hammering), a warning, not an error.
    assert result["wakilni_down"] and len(courier["fake"].calls) - calls <= 2
    assert not [r for r in caplog.records if r.levelname == "ERROR"]
    # Still down hours later: one error, once.
    since = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
    asyncio.run(db.app_state.update_one({"id": "wakilni_outage"}, {"$set": {"since": since}}))
    caplog.clear()
    with caplog.at_level("WARNING"):
        asyncio.run(sync_all_deliveries())
        asyncio.run(sync_all_deliveries())
    assert len([r for r in caplog.records if r.levelname == "ERROR" and "injoignable" in r.message]) == 1
    # Back up: the outage is over.
    courier["fake"].down = False
    courier["fake"].status_logs = [{"status": "Confirmed", "status_code": 2, "created_at": "2026-10-19 09:00:00"}]
    assert asyncio.run(sync_all_deliveries())["checked"] >= 1
    assert asyncio.run(db.app_state.find_one({"id": "wakilni_outage"})) is None


def test_the_printer_gets_wakilnis_order_number_to_write_on_the_package(client, db, courier):
    order_id = courier["order"]["id"]
    token = {"token": sign_order_action(order_id, "ready")}
    # Not before the click: the Wakilni order doesn't exist yet.
    assert "package_number" not in client.get(f"/api/order-actions/{order_id}/info", params=token).json()
    res = _ready(client, order_id).json()
    assert res["package_number"] == str(courier["fake"].delivery_id) and res["package_number_from"] == "wakilni"
    # Still there when the page is opened again.
    info = client.get(f"/api/order-actions/{order_id}/info", params=token).json()
    assert info["ready"] and info["package_number"] == str(courier["fake"].delivery_id)


def test_a_delivery_cancelled_on_wakilnis_portal_lets_go_and_a_new_one_is_made(client, db, courier):
    from app.services.delivery import sync_delivery

    order_id = courier["order"]["id"]
    _ready(client, order_id)  # clicked too early
    first_id = _order(db, order_id)["delivery"]["delivery_id"]
    # Cancelled on Wakilni's portal; the admin puts the book back to printing.
    courier["fake"].status_logs = [{"status": "Canceled", "status_code": 7, "created_at": "2026-10-20 10:00:00"}]
    asyncio.run(sync_delivery(order_id))
    order = _order(db, order_id)
    assert "delivery_id" not in order["delivery"] and order["delivery"]["cancelled"]["delivery_id"] == first_id
    assert len(courier["sent"]["problem"]) == 1 and "new one will be created" in courier["sent"]["problem"][0]
    asyncio.run(db.orders.update_one({"id": order_id}, {"$set": {"status": "printing"}}))
    # The printer's next click: a new delivery.
    courier["fake"].delivery_id += 1000
    courier["fake"].status_logs = []
    res = _ready(client, order_id).json()
    assert res["package_number"] == str(courier["fake"].delivery_id)
    assert sum("/add_delivery/" in p for _, p, _ in courier["fake"].calls) == 2


def test_cancelling_a_delivery_already_cancelled_at_wakilni(client, db, courier, monkeypatch):
    from app.core import auth

    order_id = courier["order"]["id"]
    _ready(client, order_id)
    courier["fake"].fail_cancel = True
    courier["fake"].status_logs = [{"status": "Canceled", "status_code": 7, "created_at": "2026-10-20 10:00:00"}]
    email, admin = _signup(client, db=db)
    monkeypatch.setattr(auth, "ADMIN_EMAIL", email)
    res = client.post(f"/api/admin/orders/{order_id}/delivery/cancel", headers=admin)
    assert res.status_code == 200, res.text
    assert "delivery_id" not in _order(db, order_id)["delivery"]
    # Still with Wakilni (not cancelled there): refused, kept.
    asyncio.run(db.orders.update_one({"id": order_id}, {"$set": {"status": "printing"}}))
    _ready(client, order_id)
    assert _order(db, order_id)["delivery"].get("delivery_id")
    courier["fake"].status_logs = [{"status": "Confirmed", "status_code": 2, "created_at": "2026-10-20 11:00:00"}]
    assert client.post(f"/api/admin/orders/{order_id}/delivery/cancel", headers=admin).status_code == 502


def test_putting_an_order_back_doesnt_email_the_customer_again(client, db, courier, monkeypatch):
    from app.core import auth
    from app.routers import admin as admin_router

    sent = []
    monkeypatch.setitem(admin_router.STATUS_CUSTOMER_EMAIL, "printing", lambda to, name, order: sent.append(order["status"]))
    order_id = courier["order"]["id"]
    asyncio.run(db.orders.update_one({"id": order_id}, {"$set": {"status": "ready_for_delivery"}}))
    email, admin = _signup(client, db=db)
    monkeypatch.setattr(auth, "ADMIN_EMAIL", email)
    assert client.patch(f"/api/admin/orders/{order_id}/status", json={"status": "printing"}, headers=admin).status_code == 200
    assert sent == []
    asyncio.run(db.orders.update_one({"id": order_id}, {"$set": {"status": "paid"}}))
    client.patch(f"/api/admin/orders/{order_id}/status", json={"status": "printing"}, headers=admin)
    assert sent == ["printing"]  # forward: told, as before


@pytest.fixture()
def whatsapp_on(monkeypatch):
    from app.services import whatsapp

    posted = []
    monkeypatch.setattr(whatsapp, "WHATSAPP_TOKEN", "wa-token")
    monkeypatch.setattr(whatsapp, "WHATSAPP_PHONE_NUMBER_ID", "123")
    monkeypatch.setattr(whatsapp, "WHATSAPP_PICKUP_TO", ["+961 3 111 222", "0096170333444"])
    state = {"status": 200}

    def post(url, json=None, headers=None, timeout=None):
        posted.append((url, json, headers))
        return _Res(state["status"], {"messages": [{"id": "wamid"}]} if state["status"] == 200 else {"error": {"message": "Template name does not exist"}})

    monkeypatch.setattr(whatsapp.requests, "post", post)
    return {"posted": posted, "state": state}


def test_wakilnis_team_gets_a_whatsapp_with_the_order_number(client, db, courier, whatsapp_on):
    order_id = courier["order"]["id"]
    _ready(client, order_id)
    posted = whatsapp_on["posted"]
    assert [p[1]["to"] for p in posted] == ["9613111222", "96170333444"]
    url, body, headers = posted[0]
    assert url == "https://graph.facebook.com/v23.0/123/messages" and headers["Authorization"] == "Bearer wa-token"
    assert body["type"] == "template" and body["template"]["name"] == "wakilni_pickup"
    params = [p["text"] for p in body["template"]["components"][0]["parameters"]]
    assert params == [str(courier["fake"].delivery_id), "1"]
    assert _order(db, order_id)["delivery"]["whatsapp_at"]
    _ready(client, order_id)  # a second click: no second message
    assert len(posted) == 2


def test_if_the_whatsapp_cant_be_sent_the_admin_is_told(client, db, courier, whatsapp_on):
    whatsapp_on["state"]["status"] = 400
    order_id = courier["order"]["id"]
    assert _ready(client, order_id).status_code == 200  # the printer's click still works
    assert any("WhatsApp" in p and "Template name does not exist" in p for p in courier["sent"]["problem"])
    order = _order(db, order_id)
    assert order["status"] == "ready_for_delivery" and len(order["delivery"]["whatsapp_failed"]) == 2


def test_no_whatsapp_without_its_settings(client, db, courier, monkeypatch):
    from app.services import whatsapp

    monkeypatch.setattr(whatsapp.requests, "post", lambda *a, **k: pytest.fail("nothing should be sent"))
    _ready(client, courier["order"]["id"])


def test_the_pickup_email_gives_wakilnis_order_number(monkeypatch):
    from app.services import email

    out = []
    monkeypatch.setattr(email, "DELIVERY_EMAIL", "ops@wakilni.test")
    monkeypatch.setattr(email, "send_email", lambda to, subject, body, html_body=None, **k: out.append((to, subject, body)))
    order = {"id": "abcdef12-0000", "album_title": "Byblos", "quantity": 2, "shipping_address": ADDRESS, "delivery": {"delivery_id": 9123}}
    email.send_delivery_pickup_email(order)
    to, subject, body = out[-1]
    assert to == "ops@wakilni.test" and subject == "Ready for pickup at Bookstop — Wakilni order 9123"
    assert "Wakilni order 9123 (written on the package)" in body and "Quantity: 2" in body
