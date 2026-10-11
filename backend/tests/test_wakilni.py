"""Wakilni deliveries: created when the printer marks a book ready,
followed until delivered, with a fake Wakilni answering as documented."""
import asyncio

import pytest

from app.core.signed_links import sign_order_action
from app.services.pricing import TERMS_VERSION
from tests.test_api import _signup

ADDRESS = {"full_name": "Rita Khoury Haddad", "phone": "+961 3 123 456", "street": "Rue Hamra", "building": "Bldg 5",
           "city": "Beirut", "area": "Hamra", "additional_info": "3rd floor"}


class FakeWakilni:
    """Answers like Wakilni's API and records what it was sent."""

    def __init__(self):
        self.calls = []
        self.status_logs = []
        self.fail_add = False

    def request(self, method, url, json=None, params=None, headers=None, timeout=None):
        path = url.split("wakilni.test", 1)[1]
        self.calls.append((method, path, json))
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
            return _Res(200, {"message": "Delivery order added", "delivery_id": 9001, "tracking_id": "WK123",
                              "tracking_url": "https://track.wakilni.com/WK123", "packages": []})
        if "/end_bulk/" in path:
            return _Res(200, {"message": "Closed Bulk order", "bulk_id": 77})
        if path.endswith("/orders/status"):
            return _Res(200, {"success": True, "data": {"tracking_id": "WK123", "comments": [], "logs": self.status_logs}})
        if path.endswith("/cancel"):
            return _Res(200, {"message": "Order canceled", "delivery_id": 9001})
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
    monkeypatch.setattr(delivery, "send_delivery_pickup_email", lambda order: sent["courier"].append(order["id"]))
    monkeypatch.setattr(delivery, "send_delivery_problem_email", lambda order, problem: sent["problem"].append(problem))
    monkeypatch.setattr(delivery, "send_order_shipped_email", lambda to, name, order: sent["shipped"].append(order["delivery"]["tracking_url"]))
    monkeypatch.setattr(delivery, "send_order_delivered_feedback_email", lambda to, name, order: sent["delivered"].append(order["id"]))
    monkeypatch.setattr(orders, "pdf_tasks_enabled", lambda: False)
    monkeypatch.setattr(orders, "render_album_pdf_sync", lambda *a: b"%PDF")
    monkeypatch.setattr(orders, "put_object", lambda *a, **k: {"path": a[0]})
    monkeypatch.setattr(orders, "delete_object", lambda *a, **k: None)
    monkeypatch.setattr(orders, "send_printer_order_email", lambda order: None)
    monkeypatch.setattr(orders_router, "send_order_confirmation_email", lambda *a: None)

    _, customer = _signup(client, db=db)
    album_id = client.post("/api/albums", json={"title": "Byblos", "size": "A5", "target_pages": 24}, headers=customer).json()["id"]
    asyncio.run(db.albums.update_one({"id": album_id}, {"$set": {"pages": [{"id": "1", "items": []}], "status": "ready"}}))
    order = client.post("/api/orders", json={"album_id": album_id, "shipping_address": ADDRESS, "accepted_terms_version": TERMS_VERSION}, headers=customer).json()
    return {"fake": fake, "sent": sent, "order": order, "customer": customer}


def _ready(client, order_id):
    return client.get(f"/api/order-actions/{order_id}/ready", params={"token": sign_order_action(order_id, "ready")})


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
    assert courier["sent"]["courier"] == []  # Wakilni, not the email
    _ready(client, order_id)  # a second click doesn't create a second delivery
    assert sum("start_bulk" in p for _, p, _ in courier["fake"].calls) == 1


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
    _ready(client, order_id)
    order = _order(db, order_id)
    assert "receiver area" in order["delivery"]["error"]
    assert courier["sent"]["courier"] == [order_id] and len(courier["sent"]["problem"]) == 1
    assert "/api/v2/clients/end_bulk/77" in [p for _, p, _ in courier["fake"].calls]  # the empty pickup is closed
