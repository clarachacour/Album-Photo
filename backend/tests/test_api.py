"""End-to-end tests of the real API, against an in-memory fake MongoDB.

Run from backend/ with:  pytest tests/test_api.py
No database, network or R2 access needed.
"""
import asyncio
import time
import uuid

import pytest


def _signup(client, verified=True, db=None):
    email = f"{uuid.uuid4().hex[:10]}@example.com"
    res = client.post("/api/auth/signup", json={"email": email, "password": "secret123", "name": "Test"})
    assert res.status_code == 200, res.text
    body = res.json()
    if verified:
        # Same effect as clicking the link in the verification email.
        asyncio.run(db.users.update_one({"email": email}, {"$set": {"email_verified": True}}))
    return email, {"Authorization": f"Bearer {body['token']}"}


def test_health(client):
    res = client.get("/api/")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_signup_then_me(client, db):
    email, headers = _signup(client, db=db)
    res = client.get("/api/auth/me", headers=headers)
    assert res.status_code == 200
    assert res.json()["email"] == email


def test_requests_without_token_are_rejected(client):
    assert client.get("/api/albums").status_code == 401
    bad = {"Authorization": "Bearer not-a-real-token"}
    assert client.get("/api/albums", headers=bad).status_code == 401


def test_unverified_account_cannot_create_album(client, db):
    _, headers = _signup(client, verified=False, db=db)
    res = client.post("/api/albums", json={"title": "Trip"}, headers=headers)
    assert res.status_code == 403


def test_album_create_list_get(client, db):
    _, headers = _signup(client, db=db)
    res = client.post("/api/albums", json={"title": "Sicily", "size": "A5", "target_pages": 24}, headers=headers)
    assert res.status_code == 200, res.text
    album_id = res.json()["id"]

    listed = client.get("/api/albums", headers=headers).json()
    assert [a["id"] for a in listed] == [album_id]

    album = client.get(f"/api/albums/{album_id}", headers=headers).json()
    assert album["title"] == "Sicily"
    assert album["size"] == "A5"


def test_unsupported_album_size_is_rejected(client, db):
    _, headers = _signup(client, db=db)
    res = client.post("/api/albums", json={"title": "Big", "size": "A3"}, headers=headers)
    assert res.status_code == 400


def test_users_cannot_see_each_others_albums(client, db):
    _, alice = _signup(client, db=db)
    _, bob = _signup(client, db=db)
    album_id = client.post("/api/albums", json={"title": "Private"}, headers=alice).json()["id"]

    assert client.get(f"/api/albums/{album_id}", headers=bob).status_code == 404
    assert client.patch(f"/api/albums/{album_id}", json={"title": "Hacked"}, headers=bob).status_code == 404
    assert client.get("/api/albums", headers=bob).json() == []


def test_login_with_wrong_password(client, db):
    email, _ = _signup(client, db=db)
    res = client.post("/api/auth/login", json={"email": email, "password": "wrong-password"})
    assert res.status_code == 401
    res = client.post("/api/auth/login", json={"email": email, "password": "secret123"})
    assert res.status_code == 200


def test_login_is_rate_limited_per_email(client, db, monkeypatch):
    import types

    from app.core.rate_limit import LOGIN_LIMIT_PER_EMAIL

    email, _ = _signup(client, db=db)
    limit, window = LOGIN_LIMIT_PER_EMAIL
    # Counters reset at fixed times (every `window` seconds). Freeze the
    # limiter's clock in the middle of a window so the test can't straddle a
    # reset (it once ran across 17:00:00 and saw a fresh counter). The next
    # window, not a past one: counters whose expiry date has passed are
    # deleted by the database.
    frozen = (int(time.time()) // window + 1) * window + window // 2
    monkeypatch.setattr("app.core.security.time", types.SimpleNamespace(time=lambda: frozen))
    for _ in range(limit):
        res = client.post("/api/auth/login", json={"email": email, "password": "wrong-password"})
        assert res.status_code == 401
    res = client.post("/api/auth/login", json={"email": email, "password": "wrong-password"})
    assert res.status_code == 429
    assert "Retry-After" in res.headers


@pytest.mark.parametrize(
    "origin, allowed",
    [("http://localhost:3000", True), ("https://evil.example.com", False)],
)
def test_cors_only_allows_known_origins(client, origin, allowed):
    res = client.options(
        "/api/albums",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert (res.headers.get("access-control-allow-origin") == origin) is allowed
