"""Fixes from the pre-launch security review: each test reproduces the
original problem and checks it's gone."""
import asyncio

import pytest

from tests.test_api import _signup


def _album(client, headers, **fields):
    res = client.post("/api/albums", json={"title": "Trip", **fields}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["id"]


# ---------- 1. Clients can't set server-only album fields ----------
def test_album_update_ignores_status_and_cover_image_path(client, db):
    _, headers = _signup(client, db=db)
    album_id = _album(client, headers)

    # Pointing cover_image_path at someone else's file used to be stored as is,
    # then served by /cover-image (and deleted along with the album).
    res = client.patch(
        f"/api/albums/{album_id}",
        json={"title": "Renamed", "cover_image_path": "albumai/users/alice/albums/x/photo.jpg", "status": "ready"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    album = asyncio.run(db.albums.find_one({"id": album_id}))
    assert album["title"] == "Renamed"
    assert album["cover_image_path"] is None
    assert album["status"] != "ready"
    assert client.get(f"/api/albums/{album_id}/cover-image", headers=headers).status_code == 404


# ---------- 2. Google Photos import only fetches Google's servers ----------
@pytest.mark.parametrize(
    "url, allowed",
    [
        ("https://lh3.googleusercontent.com/abc", True),
        ("https://video-downloads.googleusercontent.com/x", True),
        ("http://lh3.googleusercontent.com/abc", False),  # not https
        ("https://googleusercontent.com.evil.example/abc", False),
        ("https://evil.example/?.googleusercontent.com", False),
        ("https://user:pw@lh3.googleusercontent.com/abc", False),
        ("https://lh3.googleusercontent.com:8080/abc", False),
        ("https://169.254.169.254/computeMetadata/v1/", False),
        ("http://localhost:8000/api/", False),
        ("", False),
        (None, False),
    ],
)
def test_google_photos_url_check(url, allowed):
    from app.services.google_photos import is_google_photos_url

    assert is_google_photos_url(url) is allowed


def test_google_photos_import_never_fetches_other_addresses(client, db, monkeypatch):
    from app.services import google_photos

    fetched = []
    monkeypatch.setattr(google_photos.requests, "get", lambda url, **kw: fetched.append(url))
    _, headers = _signup(client, db=db)
    album_id = _album(client, headers)
    items = [{"mediaFile": {"baseUrl": "http://169.254.169.254/latest/meta-data", "filename": "a.jpg"}}]
    res = client.post(f"/api/albums/{album_id}/import/google-photos", json={"access_token": "t", "items": items}, headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["uploaded"] == 0
    assert fetched == []


def test_google_photos_redirect_outside_google_is_refused(monkeypatch):
    from app.services import google_photos

    class Resp:
        status_code = 302
        headers = {"Location": "http://169.254.169.254/"}

    calls = []
    monkeypatch.setattr(google_photos.requests, "get", lambda url, **kw: calls.append(url) or Resp())
    with pytest.raises(ValueError):
        google_photos._download("https://lh3.googleusercontent.com/abc=d", {})
    assert calls == ["https://lh3.googleusercontent.com/abc=d"]


# ---------- 3. The price follows the album's real page count ----------
def test_order_price_uses_the_real_page_count(client, db, monkeypatch):
    from app.routers import orders
    from app.services.pricing import compute_order_price_cents

    async def no_pdf(*args, **kwargs):
        return None

    monkeypatch.setattr(orders, "generate_order_pdf", no_pdf)
    monkeypatch.setattr(orders, "send_order_confirmation_email", lambda *a, **k: None)

    _, headers = _signup(client, db=db)
    album_id = _album(client, headers, size="A4", target_pages=250)
    pages = [{"id": str(i), "items": []} for i in range(250)]
    asyncio.run(db.albums.update_one({"id": album_id}, {"$set": {"pages": pages, "status": "ready"}}))
    # The client lowers the page count it "chose" before ordering.
    assert client.patch(f"/api/albums/{album_id}", json={"target_pages": 24}, headers=headers).status_code == 200

    address = {"full_name": "A", "phone": "1", "street": "S", "city": "C"}
    res = client.post("/api/orders", json={"album_id": album_id, "shipping_address": address}, headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["unit_price_cents"] == compute_order_price_cents("A4", 250)
    assert res.json()["unit_price_cents"] > compute_order_price_cents("A4", 24)


def test_billed_page_count():
    from app.services.pricing import billed_page_count

    assert billed_page_count({"target_pages": 50, "pages": [{}] * 30}) == 50  # chosen tier, album fell short
    assert billed_page_count({"target_pages": 24, "pages": [{}] * 60}) == 60
    assert billed_page_count({"pages": [{}] * 10}) == 10


# ---------- 4. Customer text is escaped in HTML emails ----------
def test_customer_text_is_escaped_in_emails(monkeypatch):
    from app.services import email

    sent = []
    monkeypatch.setattr(email, "send_email", lambda to, subject, body, html_body=None: sent.append(html_body))
    evil = '<a href="https://evil.example">Click</a>'
    email.send_welcome_email("victim@example.com", evil)
    email.send_order_confirmation_email("victim@example.com", evil, {"id": "o1", "total_price_cents": 100, "album_title": evil})
    monkeypatch.setattr(email, "DELIVERY_EMAIL", "delivery@example.com")
    email.send_delivery_pickup_email(
        {"id": "o1", "album_title": evil, "shipping_address": {"full_name": evil, "street": evil, "city": "C", "phone": "1", "additional_info": evil}}
    )
    assert len(sent) == 3
    for html in sent:
        assert "<a href=\"https://evil.example\">" not in html
        assert "&lt;a href=&quot;https://evil.example&quot;&gt;" in html


# ---------- 5. Long passwords don't crash the signup ----------
def test_password_longer_than_bcrypt_limit_is_refused_cleanly(client):
    too_long = client.post("/api/auth/signup", json={"email": "long@example.com", "password": "x" * 73, "name": "L"})
    assert too_long.status_code == 422
    accents = client.post("/api/auth/signup", json={"email": "long2@example.com", "password": "é" * 40, "name": "L"})
    assert accents.status_code == 422  # 80 bytes
    ok = client.post("/api/auth/signup", json={"email": "long3@example.com", "password": "x" * 72, "name": "L"})
    assert ok.status_code == 200, ok.text


# ---------- Length limits ----------
@pytest.mark.parametrize(
    "path, body",
    [
        ("/api/auth/signup", {"email": "big@example.com", "password": "secret123", "name": "x" * 100_000}),
        ("/api/contact", {"name": "A", "email": "a@example.com", "subject": "Hi", "message": "x" * 2_000_000}),
    ],
)
def test_oversized_fields_are_refused(client, path, body):
    assert client.post(path, json=body).status_code == 422


def test_album_page_count_is_bounded(client, db):
    _, headers = _signup(client, db=db)
    assert client.post("/api/albums", json={"title": "T", "target_pages": 100_000}, headers=headers).status_code == 422
    album_id = _album(client, headers)
    assert client.patch(f"/api/albums/{album_id}", json={"title": "x" * 1000}, headers=headers).status_code == 422


# ---------- Monitoring ----------
def test_monitoring_is_off_without_dsn(monkeypatch):
    from app.monitoring import init_monitoring

    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert init_monitoring() is False


def test_tokens_never_reach_sentry():
    from app.monitoring import _scrub

    event = {"request": {"url": "https://api.example/api/photos/1/image?auth=SECRET", "query_string": "auth=SECRET"}}
    out = _scrub(event, None)
    assert "SECRET" not in str(out)
