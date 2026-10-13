"""The admin can correct a printed order's delivery address — not once a
Wakilni delivery carries the old one."""
import asyncio

import pytest

from tests.test_api import _signup

NEW = {"full_name": "Rita Haddad", "phone": "70123456", "street": "Rue Sioufi", "building": "Bldg 5", "city": "Achrafieh", "area": "Achrafieh"}


@pytest.fixture()
def admin(client, db, monkeypatch):
    from app.core import auth

    email, headers = _signup(client, db=db)
    monkeypatch.setattr(auth, "ADMIN_EMAIL", email)
    return headers


def _order(db, oid, **extra):
    order = {"id": oid, "album_id": f"alb-{oid}", "user_id": "u1", "kind": "print", "status": "printing",
             "shipping_address": {"full_name": "Rita", "phone": "70123456", "street": "Wrong st", "city": "Beirut"}, **extra}
    asyncio.run(db.orders.insert_one(order))


def test_admin_can_fix_a_delivery_address(client, db, admin):
    _order(db, "addr-1")
    res = client.patch("/api/admin/orders/addr-1/shipping-address", json=NEW, headers=admin)
    assert res.status_code == 200, res.text
    assert res.json()["shipping_address"]["street"] == "Rue Sioufi"
    assert res.json()["address_history"][0]["previous"]["street"] == "Wrong st"


def test_refused_once_a_wakilni_delivery_exists(client, db, admin):
    _order(db, "addr-2", delivery={"delivery_id": 77})
    assert client.patch("/api/admin/orders/addr-2/shipping-address", json=NEW, headers=admin).status_code == 409


def test_a_customer_cannot_change_it(client, db, admin):
    _order(db, "addr-3")
    _, customer = _signup(client, db=db)
    assert client.patch("/api/admin/orders/addr-3/shipping-address", json=NEW, headers=customer).status_code == 403
