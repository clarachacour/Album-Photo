"""Authentication routes: signup, login, password, OAuth, profile."""
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from pymongo.errors import DuplicateKeyError

from app.config import ADMIN_EMAIL, APPLE_CLIENT_ID, FRONTEND_URL, GOOGLE_CLIENT_ID
from app.core.auth import (
    create_token,
    get_apple_public_key,
    get_current_user,
    get_current_user_raw,
    hash_password,
    upsert_oauth_user,
    verify_password,
)
from app.core.rate_limit import (
    FORGOT_PASSWORD_LIMIT_PER_EMAIL,
    FORGOT_PASSWORD_LIMIT_PER_IP,
    LOGIN_LIMIT_PER_EMAIL,
    LOGIN_LIMIT_PER_IP,
    rate_limiter,
)
from app.core.security import client_ip
from app.db import db
from app.schemas import (
    AppleAuthInput,
    AuthResponse,
    ChangePasswordInput,
    ForgotPasswordInput,
    GoogleAuthInput,
    LoginInput,
    ProfileUpdate,
    ResetPasswordInput,
    SignupInput,
    UserOut,
)
from app.services.email import (
    send_password_changed_email,
    send_password_reset_email,
    send_verification_email,
    send_welcome_email,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------- Auth Routes ----------
@router.post("/auth/signup", response_model=AuthResponse)
async def signup(data: SignupInput):
    existing = await db.users.find_one({"email": data.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="This email is already in use")
    user_id = str(uuid.uuid4())
    verify_token = str(uuid.uuid4())
    user_doc = {
        "id": user_id,
        "email": data.email.lower(),
        "password_hash": hash_password(data.password),
        "name": data.name,
        # Unverified until the link in the confirmation email below is
        # clicked (see verify_email) — unlike Google/Apple sign-in
        # (upsert_oauth_user), nothing here proves this address actually
        # belongs to the person signing up; anyone could type in anyone
        # else's email today. Deliberately doesn't block login or any
        # feature yet — this only tracks the fact, so it can be enforced
        # later (e.g. requiring it before ordering) without a second
        # migration to add the field retroactively.
        "email_verified": False,
        "verify_email_token": verify_token,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.users.insert_one(user_doc)
    except DuplicateKeyError:
        # The check above and this insert aren't atomic — two near-
        # simultaneous submissions of the same signup form (a double-click,
        # or the request firing twice) can both pass the find_one check
        # before either has inserted. Unlike the OAuth version of this same
        # race (see upsert_oauth_user), this always re-raises the same
        # clean "already used" error rather than ever logging the request
        # into the account that won the race — we have no way to confirm
        # this request's password actually matches that account's, and
        # silently issuing a token here would skip that check entirely.
        raise HTTPException(status_code=400, detail="This email is already in use")
    token = create_token(user_id)
    send_verification_email(data.email.lower(), data.name, verify_token, welcome=True)
    return AuthResponse(token=token, user=UserOut(id=user_id, email=data.email.lower(), name=data.name, is_admin=bool(ADMIN_EMAIL) and data.email.lower() == ADMIN_EMAIL, email_verified=False))

@router.post("/auth/login", response_model=AuthResponse)
async def login(data: LoginInput, request: Request):
    await rate_limiter.check_all([
        ("login:email", data.email, *LOGIN_LIMIT_PER_EMAIL),
        ("login:ip", client_ip(request), *LOGIN_LIMIT_PER_IP),
    ])
    user = await db.users.find_one({"email": data.email.lower()})
    if not user or not user.get("password_hash") or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    token = create_token(user["id"])
    return AuthResponse(token=token, user=UserOut(id=user["id"], email=user["email"], name=user["name"], is_admin=bool(ADMIN_EMAIL) and user["email"] == ADMIN_EMAIL, email_verified=user.get("email_verified", True)))

@router.post("/auth/forgot-password")
async def forgot_password(data: ForgotPasswordInput, request: Request):
    # Checked before looking the account up, so the limit applies the same
    # way to existing and unknown emails and can't reveal which exist.
    await rate_limiter.check_all([
        ("forgot:email", data.email, *FORGOT_PASSWORD_LIMIT_PER_EMAIL),
        ("forgot:ip", client_ip(request), *FORGOT_PASSWORD_LIMIT_PER_IP),
    ])
    user = await db.users.find_one({"email": data.email.lower()})
    # Always return the same response whether or not the account exists,
    # so this endpoint can't be used to check which emails are registered.
    if user:
        reset_token = str(uuid.uuid4())
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": {"reset_token": reset_token, "reset_token_expires": expires.isoformat()}},
        )
        reset_link = f"{FRONTEND_URL}/reset-password?token={reset_token}"
        send_password_reset_email(user["email"], user.get("name", ""), reset_link)
    return {"message": "If an account exists for this email, a reset link has been sent."}

@router.post("/auth/reset-password")
async def reset_password(data: ResetPasswordInput):
    user = await db.users.find_one({"reset_token": data.token})
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    expires = user.get("reset_token_expires")
    if not expires or datetime.fromisoformat(expires) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": hash_password(data.new_password)}, "$unset": {"reset_token": "", "reset_token_expires": ""}},
    )
    send_password_changed_email(user["email"], user.get("name", ""))
    return {"message": "Password updated"}

@router.get("/auth/verify-email")
async def verify_email(token: str = Query(...)):
    """Reached by a direct click from send_verification_email's link — no
    login involved, the token itself (stored on the user doc at signup) is
    the only proof needed. Returns a plain confirmation page rather than
    JSON, matching order_action_mark_ready's shape: a person clicking a
    link in their inbox expects to land on a page, not to receive raw
    API output."""
    user = await db.users.find_one({"verify_email_token": token})
    if not user:
        return HTMLResponse(
            "<html><body style='font-family:sans-serif; text-align:center; padding:60px;'>"
            "<h2>This confirmation link is invalid or has already been used.</h2></body></html>"
        )
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"email_verified": True}, "$unset": {"verify_email_token": ""}},
    )
    return HTMLResponse(
        "<html><body style='font-family:sans-serif; text-align:center; padding:60px;'>"
        f"<h2>Your email is confirmed — thanks!</h2>"
        f"<p><a href='{FRONTEND_URL}/dashboard'>Go to your albums</a></p></body></html>"
    )

@router.post("/auth/resend-verification")
async def resend_verification_email(user: dict = Depends(get_current_user_raw)):
    """Uses get_current_user_raw, not get_current_user — a still-
    unverified person must be able to call this despite the very
    enforcement that's blocking them from everything else, or they'd have
    no way to recover from a lost or expired first email. A no-op (not an
    error) if already verified, or if this is an OAuth account that was
    never assigned a verify_email_token in the first place — either way
    there's genuinely nothing to resend."""
    if user.get("email_verified") is not False:
        return {"message": "Your email is already verified."}
    verify_token = str(uuid.uuid4())
    await db.users.update_one({"id": user["id"]}, {"$set": {"verify_email_token": verify_token}})
    send_verification_email(user["email"], user.get("name", ""), verify_token)
    return {"message": "Verification email sent."}

@router.post("/auth/google", response_model=AuthResponse)
async def google_auth(data: GoogleAuthInput):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google sign-in is not configured on this server (GOOGLE_CLIENT_ID missing)")
    try:
        idinfo = google_id_token.verify_oauth2_token(data.credential, google_requests.Request(), GOOGLE_CLIENT_ID)
    except Exception as e:
        logger.error(f"Jeton Google invalide : {e}")
        raise HTTPException(status_code=401, detail="Invalid Google token")
    email = idinfo.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Could not read the email address of this Google account")
    user, is_new = await upsert_oauth_user(email, idinfo.get("name"), "google")
    token = create_token(user["id"])
    if is_new:
        send_welcome_email(user["email"], user["name"])
    return AuthResponse(token=token, user=UserOut(id=user["id"], email=user["email"], name=user["name"], is_admin=bool(ADMIN_EMAIL) and user["email"] == ADMIN_EMAIL))

@router.post("/auth/apple", response_model=AuthResponse)
async def apple_auth(data: AppleAuthInput):
    if not APPLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Apple sign-in is not configured on this server (APPLE_CLIENT_ID missing)")
    try:
        header = jwt.get_unverified_header(data.id_token)
        jwk_data = get_apple_public_key(header["kid"])
        if not jwk_data:
            raise ValueError("Clé publique Apple introuvable")
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk_data))
        payload = jwt.decode(
            data.id_token, public_key, algorithms=["RS256"],
            audience=APPLE_CLIENT_ID, issuer="https://appleid.apple.com",
        )
    except Exception as e:
        logger.error(f"Jeton Apple invalide : {e}")
        raise HTTPException(status_code=401, detail="Invalid Apple token")
    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Could not read the email address of this Apple account")
    user, is_new = await upsert_oauth_user(email, data.name, "apple")
    token = create_token(user["id"])
    if is_new:
        send_welcome_email(user["email"], user["name"])
    return AuthResponse(token=token, user=UserOut(id=user["id"], email=user["email"], name=user["name"], is_admin=bool(ADMIN_EMAIL) and user["email"] == ADMIN_EMAIL))

@router.get("/auth/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user_raw)):
    return UserOut(
        id=user["id"], email=user["email"], name=user["name"],
        phone=user.get("phone"), street=user.get("street"),
        building=user.get("building"), city=user.get("city"),
        additional_info=user.get("additional_info"),
        is_admin=bool(ADMIN_EMAIL) and user["email"] == ADMIN_EMAIL,
        email_verified=user.get("email_verified", True),
    )

@router.put("/auth/me", response_model=UserOut)
async def update_profile(data: ProfileUpdate, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in data.dict().items() if v is not None}
    if updates:
        await db.users.update_one({"id": user["id"]}, {"$set": updates})
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
    return UserOut(
        id=fresh["id"], email=fresh["email"], name=fresh["name"],
        phone=fresh.get("phone"), street=fresh.get("street"),
        building=fresh.get("building"), city=fresh.get("city"),
        additional_info=fresh.get("additional_info"),
    )

@router.put("/auth/password")
async def change_password(data: ChangePasswordInput, user: dict = Depends(get_current_user)):
    full_user = await db.users.find_one({"id": user["id"]})
    if not full_user or not full_user.get("password_hash") or not verify_password(data.current_password, full_user["password_hash"]):
        raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect")
    await db.users.update_one({"id": user["id"]}, {"$set": {"password_hash": hash_password(data.new_password)}})
    send_password_changed_email(full_user["email"], full_user.get("name", ""))
    return {"message": "Password updated"}
