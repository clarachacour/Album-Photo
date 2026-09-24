"""Unit tests for security.py — run from backend/ with:

    pip install -r requirements-dev.txt
    pytest tests/test_security.py

They need no database, network or environment variables (MongoDB is
replaced by an in-memory fake).
"""
import asyncio

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient
from starlette.requests import Request

from security import (
    ConfigError,
    RateLimiter,
    client_ip,
    load_jwt_secret,
    parse_cors_origins,
)


# ---------- JWT_SECRET ----------
@pytest.mark.parametrize("value", [None, "", "   ", "dev-secret", "DEV-SECRET", "changeme"])
def test_jwt_secret_missing_or_placeholder_refuses_to_start(value):
    with pytest.raises(ConfigError):
        load_jwt_secret(value)


def test_jwt_secret_real_value_is_accepted():
    secret = "x" * 48
    assert load_jwt_secret(secret) == secret


def test_jwt_secret_short_value_is_accepted_with_warning(caplog):
    assert load_jwt_secret("short-but-real") == "short-but-real"
    assert "recommended" in caplog.text


# ---------- CORS ----------
def test_cors_wildcard_is_never_allowed():
    assert parse_cors_origins("*", None) == []
    assert parse_cors_origins("*", "https://everbook.app") == ["https://everbook.app"]


def test_cors_list_is_cleaned_and_includes_frontend_url():
    origins = parse_cors_origins(
        " https://a.com/ , https://b.com,,https://a.com", "https://front.com/"
    )
    assert origins == ["https://a.com", "https://b.com", "https://front.com"]


def test_cors_unset_falls_back_to_frontend_url():
    assert parse_cors_origins(None, "http://localhost:3000") == ["http://localhost:3000"]


# ---------- Client IP ----------
def _request(headers=None, client=("10.0.0.1", 1234)):
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": client,
    }
    return Request(scope)


def test_client_ip_uses_last_forwarded_entry_not_the_spoofable_first():
    req = _request({"X-Forwarded-For": "1.1.1.1, 203.0.113.7"})
    assert client_ip(req) == "203.0.113.7"


def test_client_ip_falls_back_to_socket_address():
    assert client_ip(_request()) == "10.0.0.1"


# ---------- Rate limiter ----------
def _limiter(enabled=True):
    return RateLimiter(AsyncMongoMockClient()["test"]["rate_limits"], enabled=enabled)


def test_rate_limiter_blocks_after_limit_with_retry_after():
    limiter = _limiter()

    async def scenario():
        for _ in range(3):
            await limiter.hit("login:email", "a@b.com", limit=3, window_seconds=60)
        with pytest.raises(HTTPException) as exc:
            await limiter.hit("login:email", "a@b.com", limit=3, window_seconds=60)
        return exc.value

    err = asyncio.run(scenario())
    assert err.status_code == 429
    assert 1 <= int(err.headers["Retry-After"]) <= 60


def test_rate_limiter_keys_are_independent_and_case_insensitive():
    limiter = _limiter()

    async def scenario():
        await limiter.hit("login:email", "A@B.com", limit=1, window_seconds=60)
        # Same email with different case counts as the same person…
        with pytest.raises(HTTPException):
            await limiter.hit("login:email", "a@b.com", limit=1, window_seconds=60)
        # …but another email, or another scope, has its own counter.
        await limiter.hit("login:email", "other@b.com", limit=1, window_seconds=60)
        await limiter.hit("forgot:email", "a@b.com", limit=1, window_seconds=60)

    asyncio.run(scenario())


def test_rate_limiter_does_not_store_raw_emails():
    limiter = _limiter()

    async def scenario():
        await limiter.hit("login:email", "secret@person.com", limit=5, window_seconds=60)
        return await limiter.collection.find_one({})

    doc = asyncio.run(scenario())
    assert "secret@person.com" not in doc["_id"]
    assert doc["expires_at"] is not None


def test_rate_limiter_can_be_disabled():
    limiter = _limiter(enabled=False)

    async def scenario():
        for _ in range(10):
            await limiter.hit("contact:ip", "1.2.3.4", limit=1, window_seconds=60)

    asyncio.run(scenario())
