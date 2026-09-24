"""Security helpers: required secrets, CORS origins and rate limiting.

Kept free of any app import so it can be tested without starting the app.
"""
from __future__ import annotations

import hashlib
import logging
import math
import time
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from fastapi import HTTPException, Request
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JWT secret
# ---------------------------------------------------------------------------
# Values that must never be accepted as a real secret: the old hard-coded
# fallback, plus obvious placeholders someone might copy from an example file.
_FORBIDDEN_SECRETS = {"dev-secret", "changeme", "change-me", "secret", "your-secret-here"}
# 32 characters ≈ 256 bits of randomness when generated with
# `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
RECOMMENDED_SECRET_LENGTH = 32


class ConfigError(RuntimeError):
    """Raised at startup when a required setting is missing or unsafe."""


def load_jwt_secret(value: Optional[str]) -> str:
    """Return the JWT secret, or refuse to start the app.

    Anyone who knows this secret can forge a login token for any account
    (and forge the signed links sent to the printer), so there is no safe
    default: the server stops immediately with a clear message instead.
    """
    secret = (value or "").strip()
    if not secret:
        raise ConfigError(
            "JWT_SECRET is not set. Generate one with "
            "`python -c \"import secrets; print(secrets.token_urlsafe(48))\"` "
            "and set it as an environment variable (a different value for dev and prod)."
        )
    if secret.lower() in _FORBIDDEN_SECRETS:
        raise ConfigError(
            "JWT_SECRET is set to a placeholder value. Replace it with a long random value."
        )
    if len(secret) < RECOMMENDED_SECRET_LENGTH:
        # Not fatal, so an existing deployment with a shorter (but real)
        # secret keeps working — but it shows up in the logs.
        logger.warning(
            "JWT_SECRET is only %d characters long; at least %d random characters are recommended.",
            len(secret), RECOMMENDED_SECRET_LENGTH,
        )
    return secret


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
def parse_cors_origins(raw: Optional[str], frontend_url: Optional[str]) -> List[str]:
    """Build the explicit list of websites allowed to call the API from a browser.

    - CORS_ORIGINS is a comma-separated list, e.g.
      "https://everbook.com,https://www.everbook.com".
    - FRONTEND_URL is always added, so the site the emails link to works
      even if CORS_ORIGINS was forgotten.
    - "*" (any website) is ignored on purpose, with a warning in the logs.
    """
    origins: List[str] = []
    for part in (raw or "").split(","):
        origin = part.strip().rstrip("/")
        if not origin:
            continue
        if origin == "*":
            logger.warning(
                "CORS_ORIGINS contains '*', which is ignored: list the exact frontend URLs instead."
            )
            continue
        if origin not in origins:
            origins.append(origin)
    frontend = (frontend_url or "").strip().rstrip("/")
    if frontend and frontend not in origins:
        origins.append(frontend)
    return origins


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
def client_ip(request: Request) -> str:
    """Best-effort address of the visitor.

    On Cloud Run, the app sits behind Google's front end, so
    request.client.host is Google's address, not the visitor's. Google adds
    the real visitor address as the *last* entry of X-Forwarded-For.
    Earlier entries can be typed in by the visitor themself, so they are
    never trusted.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        last = forwarded.split(",")[-1].strip()
        if last:
            return last
    return request.client.host if request.client else "unknown"


def _hash_key(value: str) -> str:
    # Store a hash instead of the raw email/IP: the counters only need to
    # tell visitors apart, not know who they are.
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()[:32]


class RateLimiter:
    """Fixed-window counters stored in MongoDB.

    MongoDB rather than the server's memory because Cloud Run can run
    several copies of the backend at once: counters kept in memory would be
    per copy (and reset on every restart), so an attacker would get N times
    the limit. A TTL index makes MongoDB delete old counters by itself.
    """

    def __init__(self, collection, enabled: bool = True):
        self.collection = collection
        self.enabled = enabled

    async def ensure_indexes(self) -> None:
        await self.collection.create_index("expires_at", expireAfterSeconds=0)

    async def hit(self, scope: str, key: str, limit: int, window_seconds: int) -> None:
        """Count one attempt; raise HTTP 429 once `limit` is exceeded in the window."""
        if not self.enabled:
            return
        now = time.time()
        window_start = int(now // window_seconds) * window_seconds
        doc_id = f"{scope}:{_hash_key(key)}:{window_start}"
        update = {
            "$inc": {"count": 1},
            "$setOnInsert": {
                "expires_at": datetime.fromtimestamp(window_start + window_seconds, tz=timezone.utc),
            },
        }
        try:
            doc = await self.collection.find_one_and_update(
                {"_id": doc_id}, update, upsert=True, return_document=ReturnDocument.AFTER
            )
        except DuplicateKeyError:
            # Two requests created the same counter at the same instant; the
            # other one won, so just increment the existing document.
            doc = await self.collection.find_one_and_update(
                {"_id": doc_id}, update, return_document=ReturnDocument.AFTER
            )
        except Exception:
            # Never lock everyone out because the counter itself failed.
            logger.exception("Rate limiter unavailable; letting the request through")
            return
        if doc and doc.get("count", 0) > limit:
            retry_after = max(1, math.ceil(window_start + window_seconds - now))
            raise HTTPException(
                status_code=429,
                detail="Too many attempts. Please wait a few minutes and try again.",
                headers={"Retry-After": str(retry_after)},
            )

    async def check_all(self, checks: Iterable[tuple]) -> None:
        """Apply several (scope, key, limit, window_seconds) limits in turn."""
        for scope, key, limit, window in checks:
            if key:
                await self.hit(scope, key, limit, window)

