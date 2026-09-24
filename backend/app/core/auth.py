"""Passwords, login tokens, OAuth helpers and the "current user" dependencies."""
import time as _time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
import requests
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pymongo.errors import DuplicateKeyError

from app.config import ADMIN_EMAIL, JWT_ALGORITHM, JWT_EXP_HOURS, JWT_SECRET
from app.db import db


# ---------- Auth ----------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False

def create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXP_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None

bearer_scheme = HTTPBearer(auto_error=False)

_apple_jwks_cache = {"keys": None, "fetched_at": 0}

def get_apple_public_key(kid: str):
    if not _apple_jwks_cache["keys"] or _time.time() - _apple_jwks_cache["fetched_at"] > 3600:
        resp = requests.get("https://appleid.apple.com/auth/keys", timeout=5)
        resp.raise_for_status()
        _apple_jwks_cache["keys"] = resp.json()["keys"]
        _apple_jwks_cache["fetched_at"] = _time.time()
    for key in _apple_jwks_cache["keys"]:
        if key["kid"] == kid:
            return key
    return None

async def upsert_oauth_user(email: str, name: str, provider: str) -> tuple:
    """Returns (user, is_new) — is_new is what callers use to decide
    whether to send the welcome email (only on a genuinely new account,
    never on a routine sign-in to an existing one)."""
    email = email.lower()
    user = await db.users.find_one({"email": email})
    if user:
        return user, False
    user_id = str(uuid.uuid4())
    user_doc = {
        "id": user_id,
        "email": email,
        "password_hash": None,
        "name": name or email.split("@")[0],
        "auth_provider": provider,
        # Google/Apple have already confirmed this address belongs to the
        # person signing in — asking them to also click a verification
        # link we'd send would be a redundant, confusing extra step for
        # an email that's already proven. Only the plain signup path
        # (below) starts unverified and needs its own confirmation link.
        "email_verified": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.users.insert_one(user_doc)
    except DuplicateKeyError:
        # The check above and this insert aren't atomic — two near-
        # simultaneous sign-in attempts for the same brand-new email (seen
        # in practice: a browser firing the OAuth callback twice) can both
        # pass the find_one check before either has inserted, and the
        # second one collides with the unique email index here instead of
        # actually being a real conflict. The other request's insert
        # already created the account we were about to, so just use that
        # one instead of surfacing a 500 for what is, from the user's
        # perspective, a completely normal sign-in.
        existing = await db.users.find_one({"email": email})
        if existing:
            return existing, False
        raise
    return user_doc, True

async def get_current_user_raw(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    """The actual token -> user lookup, with no email-verification check —
    used directly by the couple of endpoints an unverified person still
    needs (checking their own status, asking for a fresh verification
    email) so they aren't locked out of finding out *why* they're locked
    out. Every other endpoint should depend on get_current_user below
    instead, which wraps this with that enforcement."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = decode_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def get_current_user(user: dict = Depends(get_current_user_raw)) -> dict:
    """The dependency almost every endpoint in this file uses. Blocks
    access outright for a classic (email/password) signup that hasn't
    clicked its verification link yet — email_verified is explicitly set
    to False at signup (see signup) and only becomes True once
    verify_email runs. Deliberately checks `is False`, not falsy: every
    account that existed before this feature shipped, and every Google/
    Apple account (see upsert_oauth_user), has no email_verified field at
    all (None) or is already True — neither should ever be blocked by a
    check that was never meant to apply to them retroactively."""
    if user.get("email_verified") is False:
        raise HTTPException(status_code=403, detail="Please verify your email address before continuing.")
    return user

def require_admin(user: dict):
    """Every admin endpoint below hand-checks this rather than something
    reusable via Depends() — deliberately simple for a single-admin
    business rather than building out a whole role system for one person's
    account."""
    if not ADMIN_EMAIL or user.get("email") != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Non autorisé")
