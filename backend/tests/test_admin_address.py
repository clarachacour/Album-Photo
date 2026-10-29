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


def test_the_country_is_lebanon_and_nothing_else(client, db, admin):
    _order(db, "addr-4")
    res = client.patch("/api/admin/orders/addr-4/shipping-address", json=NEW, headers=admin)
    assert res.json()["shipping_address"]["country"] == "Lebanon"
    _order(db, "addr-5")
    assert client.patch("/api/admin/orders/addr-5/shipping-address", json={**NEW, "country": "France"}, headers=admin).status_code == 422


def test_the_setup_check_says_what_is_set_never_the_values(client, admin, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "WAKILNI_URL", "https://api-dev.wakilni.com")
    rows = client.get("/api/admin/setup-check", headers=admin).json()
    by_key = {r["key"]: r for r in rows}
    assert by_key["wakilni_live"]["ok"] is False and "api-dev" in by_key["wakilni_live"]["hint"]
    assert all(set(r) == {"key", "ok", "label", "hint"} for r in rows)
    assert "e2e-" not in str(rows) and "secret" not in str(rows).lower().replace("cleanup_secret", "").replace("wakilni_secret", "")


def test_the_setup_check_is_for_the_admin_only(client, db):
    _, headers = _signup(client, db=db)
    assert client.get("/api/admin/setup-check", headers=headers).status_code == 403
