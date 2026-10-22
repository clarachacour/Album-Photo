"""Reminder emails: a cart left as it is, an album started and never
ordered — once each, in the customer's language, during the day, and never
again once stopped."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_api import _signup

NOON = datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc)  # 12:00/13:00 in Beirut


@pytest.fixture()
def mails(monkeypatch):
    from app.services import reminders

    sent = []
    monkeypatch.setattr(reminders, "send_cart_reminder_email", lambda to, name, lines, lang, stop: sent.append(("cart", to, lines, lang, stop)))
    monkeypatch.setattr(reminders, "send_unfinished_album_reminder_email", lambda to, name, album, stop: sent.append(("album", to, album["id"], album.get("lang"), stop)))
    monkeypatch.setattr(reminders, "send_album_expiring_soon_email", lambda to, name, album, days: sent.append(("expiring", to, album["id"], days)))
    return sent


def _customer(client, db, lang="fr"):
    email, headers = _signup(client, db=db)
    album_id = client.post("/api/albums", json={"title": "Byblos", "size": "A5", "target_pages": 24, "lang": lang}, headers=headers).json()["id"]
    asyncio.run(db.albums.update_one({"id": album_id}, {"$set": {"pages": [{"id": "1", "items": []}], "status": "ready"}}))
    user = asyncio.run(db.users.find_one({"email": email}))
    return email, headers, album_id, user["id"]


def _run(now=NOON):
    from app.services.reminders import send_reminders

    return asyncio.run(send_reminders(now))


def _age(db, collection, query, hours):
    when = (NOON - timedelta(hours=hours)).isoformat()
    asyncio.run(getattr(db, collection).update_many(query, {"$set": {"updated_at": when, "created_at": when}}))


def test_a_cart_left_a_day_gets_one_reminder_in_the_customers_language(client, db, mails):
    email, headers, album_id, user_id = _customer(client, db)
    assert client.post("/api/cart/items", json={"album_id": album_id, "kind": "print", "quantity": 1}, headers=headers).status_code == 200
    _age(db, "carts", {"user_id": user_id}, 5)
    _run()
    assert not [m for m in mails if m[1] == email]  # not yet: 5 hours only
    _age(db, "carts", {"user_id": user_id}, 25)
    _run()
    mine = [m for m in mails if m[1] == email]
    assert [(m[0], m[2], m[3]) for m in mine] == [("cart", [("Byblos", "print")], "fr")]
    _run()
    assert len([m for m in mails if m[1] == email]) == 1  # once
    # The album in the cart: no "finish your album" email on top.
    _age(db, "albums", {"id": album_id}, 24 * 4)
    _run()
    assert [m[0] for m in mails if m[1] == email] == ["cart"]


def test_an_album_never_ordered_gets_one_reminder(client, db, mails):
    email, headers, album_id, user_id = _customer(client, db, lang="en")
    _age(db, "albums", {"id": album_id}, 24 * 4)
    _run()
    _run()
    mine = [m for m in mails if m[1] == email]
    assert [(m[0], m[2], m[3]) for m in mine] == [("album", album_id, "en")]


def test_no_reminder_for_an_album_left_long_ago(client, db, mails):
    email, headers, album_id, user_id = _customer(client, db)
    _age(db, "albums", {"id": album_id}, 24 * 20)
    _run()
    assert not [m for m in mails if m[1] == email]


def test_nothing_is_sent_at_night(client, db, mails):
    email, headers, album_id, user_id = _customer(client, db)
    _age(db, "albums", {"id": album_id}, 24 * 4)
    assert _run(NOON.replace(hour=1)) == {"reminders": "outside sending hours"}
    assert not [m for m in mails if m[1] == email]


def test_the_link_in_the_email_stops_them(client, db, mails):
    from app.services.reminders import stop_url

    email, headers, album_id, user_id = _customer(client, db)
    link = stop_url(user_id)
    assert client.get("/api/reminders/stop", params={"user": user_id, "token": "forged"}).status_code == 403
    res = client.get("/api" + link.split("/api", 1)[1])
    assert res.status_code == 200 and "Vous ne recevrez plus de rappels" in res.text
    _age(db, "albums", {"id": album_id}, 24 * 4)
    _run()
    assert not [m for m in mails if m[1] == email]


def test_the_scheduled_job_sends_them(client, db, mails, monkeypatch):
    from app.routers import internal

    monkeypatch.setattr(internal, "CLEANUP_SECRET", "s3cret")
    calls = []

    async def fake_reminders():
        calls.append(1)
        return {"carts_reminded": 0}

    monkeypatch.setattr(internal, "send_reminders", fake_reminders)
    monkeypatch.setattr(internal, "flush_printer_queue", lambda: asyncio.sleep(0, 0))
    res = client.post("/api/internal/sync-deliveries", headers={"x-cleanup-secret": "s3cret"})
    assert res.status_code == 200 and res.json()["carts_reminded"] == 0 and calls == [1]


def test_the_emails_read_well_in_both_languages(monkeypatch):
    from app.services import email

    out = []
    monkeypatch.setattr(email, "send_email", lambda to, subject, body, html_body=None, **k: out.append((subject, body, html_body)))
    email.send_cart_reminder_email("a@b.c", "Rita", [("Byblos <3", "print"), ("A4 · 50 pages", "gift")], "fr", "https://api/stop")
    subject, body, html = out[-1]
    assert subject == "Votre album vous attend dans votre panier"
    assert "Bonjour Rita," in body and "• Byblos <3 — album imprimé" in body and "• A4 · 50 pages — carte cadeau" in body
    assert "Byblos &lt;3" in html and "https://api/stop" in html and "/cart" in html
    email.send_unfinished_album_reminder_email("a@b.c", "", {"id": "x1", "title": "Paros", "lang": "en"}, "https://api/stop")
    subject, body, html = out[-1]
    assert subject == "Finish your Everbook album — Paros" and body.startswith("Hi,") and "/editor/x1" in html
