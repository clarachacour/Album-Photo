"""The team's order inbox hears when the printer marks a book ready (test
phase only) and when an order is delivered."""
import asyncio

import pytest


@pytest.fixture()
def sent(app, monkeypatch):
    from app.services import email as email_module

    out = []
    monkeypatch.setattr(email_module, "ORDERS_EMAIL", "orders@everbook.test")
    monkeypatch.setattr(email_module, "send_email", lambda to, subject, body, html_body=None, reply_to=None: out.append((to, subject, body)))
    return out


def _order(db, oid):
    order = {"id": oid, "album_id": f"alb-{oid}", "user_id": "u1", "kind": "print", "status": "printing", "album_title": "Sicily",
             "total_price_cents": 500, "shipping_price_cents": 500, "unit_price_cents": 0,
             "shipping_address": {"full_name": "Rita Haddad", "phone": "70123456", "street": "Rue Sioufi", "city": "Beirut"}}
    asyncio.run(db.orders.insert_one(order))


def _ready(client, monkeypatch, oid):
    from app.core.signed_links import sign_order_action
    from app.routers import orders as orders_router

    async def fake_dispatch(order_id):
        return await orders_router.db.orders.find_one({"id": order_id}, {"_id": 0})

    monkeypatch.setattr(orders_router, "dispatch_delivery", fake_dispatch)
    return client.post(f"/api/order-actions/{oid}/ready?token={sign_order_action(oid, 'ready')}")


@pytest.mark.free_trial
def test_ready_for_pickup_is_emailed_to_orders_during_the_test_phase(client, db, sent, monkeypatch):
    from app.services import pricing

    monkeypatch.setattr(pricing, "FREE_TRIAL", True)
    _order(db, "5f4c0509-team1")
    assert _ready(client, monkeypatch, "5f4c0509-team1").status_code == 200
    team = [s for s in sent if s[0] == "orders@everbook.test"]
    assert len(team) == 1 and "Ready for pickup" in team[0][1] and "EB-5F4C0509" in team[0][1]
    assert "$" not in team[0][2]


def test_not_after_the_test_phase(client, db, sent, monkeypatch):
    _order(db, "5f4c0509-team2")
    _ready(client, monkeypatch, "5f4c0509-team2")
    assert not [s for s in sent if s[0] == "orders@everbook.test"]


def test_delivered_is_emailed_to_orders(app, sent):
    from app.services import email as email_module

    email_module.send_team_order_update_email({"id": "5f4c0509-x", "album_title": "Sicily", "shipping_address": {}}, "delivered")
    assert sent and sent[0][0] == "orders@everbook.test" and "[Delivered] EB-5F4C0509" in sent[0][1]
