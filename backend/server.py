import sys
import asyncio 


if sys.platform == "win32":
    # The default Windows event loop (Selector) can't spawn subprocesses,
    # which is exactly what Playwright needs to launch the browser for PDF
    # export — without this, it fails with NotImplementedError. Must be set
    # before uvicorn/FastAPI create their event loop, so this needs to run
    # at import time, before anything else touches asyncio.
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form, Header, Query, BackgroundTasks
from fastapi.responses import Response, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from pathlib import Path
from io import BytesIO
import os
import logging
import uuid
import json
import math
import base64
import bcrypt
import jwt
import requests
import re
import asyncio
from PIL import Image, ExifTags
try:
    import pillow_heif
    pillow_heif.register_heif_opener()  # lets Image.open() read iPhone HEIC/HEIF photos — plain Pillow can't decode them on its own
except ImportError:
    logging.getLogger(__name__).warning("pillow-heif non installé — les photos HEIC/HEIF (format par défaut iPhone) échoueront au décodage")
import numpy as np
import smtplib
from email.mime.text import MIMEText
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
import time as _time

# ReportLab for PDF export
from reportlab.lib.pagesizes import A3, A4, A5, landscape, portrait
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors as rl_colors
from reportlab.pdfbase import pdfmetrics
from playwright.sync_api import sync_playwright
from reportlab.pdfbase.ttfonts import TTFont

# Register the same fonts the web editor uses, so PDF text isn't silently
# swapped for a generic fallback (Helvetica) that looks nothing like it.
import cover_fonts as _cf
import tempfile as _tempfile
import os as _os

_FONT_DIR = _os.path.join(_tempfile.gettempdir(), "albumai_fonts")
_os.makedirs(_FONT_DIR, exist_ok=True)

_WEB_FONTS = {
    "Baloo2-ExtraBold": _cf.BALOO2_EXTRABOLD,
    "Manrope-Regular": _cf.MANROPE_REGULAR,
    "Manrope-Bold": _cf.MANROPE_BOLD,
    "CormorantGaramond-Regular": _cf.CORMORANT_REGULAR,
    "CormorantGaramond-Bold": _cf.CORMORANT_BOLD,
}
for _font_name, _font_bytes in _WEB_FONTS.items():
    _font_path = _os.path.join(_FONT_DIR, f"{_font_name}.ttf")
    if not _os.path.exists(_font_path):
        with open(_font_path, "wb") as _fh:
            _fh.write(_font_bytes)
    pdfmetrics.registerFont(TTFont(_font_name, _font_path))

# The web editor renders a single book page at roughly this many CSS pixels
# wide — font sizes chosen in the editor (title_font_size, item font_size)
# are stored as raw px calibrated against that width. PDF pages are measured
# in points at their real print size, so a size stored as "48" needs scaling
# by (actual page width in points / this reference) to look the same
# proportion of the page as it did in the editor, not the same raw number.
REFERENCE_PAGE_PX = 430

def resolve_pdf_font(css_font: str, weight: str = "normal") -> str:
    """Maps a CSS font-family string (as stored on cover/text items) to the
    matching registered PDF font, falling back to Manrope if unrecognized."""
    css_font = (css_font or "").lower()
    is_bold = str(weight).lower() in ("bold", "600", "700", "800", "900") or (
        str(weight).isdigit() and int(weight) >= 600
    )
    if "baloo" in css_font:
        return "Baloo2-ExtraBold"  # only the extra-bold cut was bundled — it's the only weight used by the app
    if "cormorant" in css_font:
        return "CormorantGaramond-Bold" if is_bold else "CormorantGaramond-Regular"
    if "courier" in css_font:
        return "Courier-Bold" if is_bold else "Courier"
    if "georgia" in css_font or "helvetica" in css_font or "arial" in css_font:
        return "Helvetica-Bold" if is_bold else "Helvetica"
    # Manrope (the app's default sans-serif) and anything unrecognized
    return "Manrope-Bold" if is_bold else "Manrope-Regular"

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# ---------- Config ----------
MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']
JWT_SECRET = os.environ.get('JWT_SECRET', 'dev-secret')
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')
JWT_EXP_HOURS = 24 * 30
APP_NAME = os.environ.get('APP_NAME', 'albumai')
# How many photos get processed at once (uploads) / analyzed at once (AI).
# Each one held in memory means the *decoded* image, not just the file size
# — a single 12MP JPEG can take 30-50MB once decoded. On a small instance
# (e.g. Render's 512MB Starter plan), running 8 at once was enough to run
# out of memory on a batch of ordinary phone photos. Lower default here,
# safely raise via env var once on a larger instance — no code change needed.
UPLOAD_CONCURRENCY = int(os.environ.get("UPLOAD_CONCURRENCY", "3"))
AI_CONCURRENCY = int(os.environ.get("AI_CONCURRENCY", "3"))
# Deliberately separate from — and lower than — UPLOAD_CONCURRENCY: this
# one bounds simultaneous connections to Google's own servers (Google
# Photos import), not our own R2 bucket, and pushing it as high as
# UPLOAD_CONCURRENCY caused Google to start dropping connections
# (SSLEOFError / "Max retries exceeded") under load.
GOOGLE_PHOTOS_CONCURRENCY = int(os.environ.get("GOOGLE_PHOTOS_CONCURRENCY", "4"))
# Shared secret Cloud Scheduler must send to trigger the 30-day draft-album
# purge (see /internal/cleanup-expired-albums) — without it, anyone who
# finds the URL could wipe every never-ordered album on demand.
CLEANUP_SECRET = os.environ.get("CLEANUP_SECRET")
DRAFT_ALBUM_RETENTION_DAYS = int(os.environ.get("DRAFT_ALBUM_RETENTION_DAYS", "30"))

# ---------- Mongo ----------
# Explicitly point at certifi's CA bundle — on some fresh Python installs
# (especially newer/pre-release versions on Windows), the system's default
# certificate store isn't picked up automatically, causing
# "CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate".
import certifi
client = AsyncIOMotorClient(MONGO_URL, tlsCAFile=certifi.where())
db = client[DB_NAME]

# ---------- App ----------
app = FastAPI(title="Album AI Studio API")
api_router = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --------- Storage helpers (Cloudflare R2 — S3-compatible object storage) ----------
# Files never live on the app server's own disk: uploads/thumbnails/PDFs go
# straight to R2, which is durable, cheap, and independent of whichever
# machine happens to be running the backend at any given moment (important
# since Render's free/starter instances don't guarantee the same disk
# across redeploys or restarts).
import boto3
from botocore.config import Config as BotoConfig

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "album-photo")

_r2_client = None

def get_r2_client():
    global _r2_client
    if _r2_client is None:
        if not (R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY):
            raise RuntimeError(
                "R2 storage is not configured — set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, "
                "R2_SECRET_ACCESS_KEY and R2_BUCKET_NAME in the environment."
            )
        _r2_client = boto3.client(
            "s3",
            endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            config=BotoConfig(signature_version="s3v4"),
            region_name="auto",
        )
    return _r2_client

# Images packagées avec l'application (ex: logo corail par défaut sur la couverture)
# Embarquées en base64 (voir cover_assets.py) pour ne jamais dépendre d'un fichier
# présent sur le disque — évite les soucis de fichier oublié lors d'un déploiement.
from cover_assets import CORAL_LOGO_BYTES
from theme_assets import (
    TRAVEL_SICILY_ICON, TRAVEL_HAWAII_ICON, TRAVEL_THAILAND_ICON,
    TRAVEL_PAROS_ICON, TRAVEL_MOROCCO_ICON, TRAVEL_AUSTRALIA_ICON,
    TRAVEL_BARCELONA_ICON,
)
BUNDLED_ASSETS_BYTES = {
    "coral": CORAL_LOGO_BYTES,
    "travel_sicily": TRAVEL_SICILY_ICON,
    "travel_hawaii": TRAVEL_HAWAII_ICON,
    "travel_thailand": TRAVEL_THAILAND_ICON,
    "travel_paros": TRAVEL_PAROS_ICON,
    "travel_morocco": TRAVEL_MOROCCO_ICON,
    "travel_australia": TRAVEL_AUSTRALIA_ICON,
    "travel_barcelona": TRAVEL_BARCELONA_ICON,
}

def init_storage() -> Optional[str]:
    """Verifies R2 is reachable and the bucket exists at startup, so a
    misconfiguration is caught immediately in the logs rather than on the
    first photo upload."""
    try:
        get_r2_client().head_bucket(Bucket=R2_BUCKET_NAME)
        return "r2_storage_active"
    except Exception as e:
        logger.error(f"R2 storage is not reachable at startup: {e}")
        return None

def put_object(path, data, content_type=None):
    """Uploads bytes to R2 and returns a dict with the path and size —
    same shape as the old local-disk version, so every caller is unaffected."""
    get_r2_client().put_object(
        Bucket=R2_BUCKET_NAME,
        Key=path,
        Body=data,
        ContentType=content_type or "application/octet-stream",
    )
    return {"path": path, "size": len(data)}

def get_object(path: str) -> tuple:
    """Downloads bytes from R2 — same (content, content_type) return shape
    as the old local-disk version."""
    try:
        resp = get_r2_client().get_object(Bucket=R2_BUCKET_NAME, Key=path)
    except Exception as e:
        raise HTTPException(status_code=404, detail="Image non trouvée")
    content = resp["Body"].read()
    content_type = resp.get("ContentType") or "image/jpeg"
    return content, content_type

def delete_object(path: str) -> None:
    """Deletes one object from R2. Never raises — a missing/already-deleted
    object is not an error for a cleanup operation, and callers (order-time
    cleanup, the 30-day draft purge) run in bulk and shouldn't abort the
    whole batch over one object that's already gone."""
    if not path:
        return
    try:
        get_r2_client().delete_object(Bucket=R2_BUCKET_NAME, Key=path)
    except Exception as e:
        logger.debug(f"Impossible de supprimer {path} de R2 (probablement déjà supprimé) : {e}")

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

# ---------- Email (password reset) ----------
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER or "no-reply@albumai.local")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

def send_email(to_email: str, subject: str, body: str):
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        # No email provider configured — log it so it's usable in local/dev
        # testing without silently failing. Set SMTP_HOST/SMTP_USER/
        # SMTP_PASSWORD to send real emails.
        logger.warning(f"[DEV] SMTP non configuré — email non envoyé à {to_email} : {subject}\n{body}")
        return
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to_email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to_email], msg.as_string())
    except Exception as e:
        logger.error(f"Échec de l'envoi de l'email à {to_email} : {e}")

def send_password_reset_email(to_email: str, name: str, reset_link: str):
    subject = "Reset your password"
    body = (
        f"Hi {name or ''},\n\n"
        f"Click the link below to reset your password (valid for 1 hour):\n{reset_link}\n\n"
        f"If you didn't request this, you can safely ignore this email."
    )
    send_email(to_email, subject, body)

def send_order_confirmation_email(to_email: str, name: str, order: dict):
    order_url = f"{FRONTEND_URL}/orders/{order['id']}"
    total = order.get("total_price_cents", 0) / 100
    subject = "Your Everbook order is confirmed"
    body = (
        f"Hi {name or ''},\n\n"
        f"Thanks for your order! We've received it and will start preparing your book.\n\n"
        f"Order total: {total:.2f} {order.get('currency', 'eur').upper()}\n"
        f"Quantity: {order.get('quantity', 1)}\n\n"
        f"You can follow its status here:\n{order_url}\n\n"
        f"We'll email you again once it ships."
    )
    send_email(to_email, subject, body)

def send_order_shipped_email(to_email: str, name: str, order: dict):
    order_url = f"{FRONTEND_URL}/orders/{order['id']}"
    tracking = order.get("tracking_number")
    subject = "Your Everbook order is on its way"
    body = (
        f"Hi {name or ''},\n\n"
        f"Good news — your book has shipped!\n\n"
        + (f"Tracking number: {tracking}\n\n" if tracking else "")
        + f"You can follow its status here:\n{order_url}"
    )
    send_email(to_email, subject, body)

def send_order_delivered_feedback_email(to_email: str, name: str, order: dict):
    contact_url = f"{FRONTEND_URL}/contact"
    subject = "How did your Everbook turn out?"
    body = (
        f"Hi {name or ''},\n\n"
        f"Your book should have arrived by now — we hope you love it!\n\n"
        f"We'd love to hear what you thought, or know right away if anything wasn't right:\n{contact_url}\n\n"
        f"Thank you for printing with Everbook."
    )
    send_email(to_email, subject, body)

# ---------- OAuth (Google / Apple) ----------
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
APPLE_CLIENT_ID = os.environ.get("APPLE_CLIENT_ID")  # Apple "Services ID"

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

async def upsert_oauth_user(email: str, name: str, provider: str) -> dict:
    email = email.lower()
    user = await db.users.find_one({"email": email})
    if user:
        return user
    user_id = str(uuid.uuid4())
    user_doc = {
        "id": user_id,
        "email": email,
        "password_hash": None,
        "name": name or email.split("@")[0],
        "auth_provider": provider,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user_doc)
    return user_doc

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = decode_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# ---------- Models ----------
class SignupInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1)

class LoginInput(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: str
    email: str
    name: str
    phone: Optional[str] = None
    street: Optional[str] = None
    building: Optional[str] = None
    city: Optional[str] = None
    additional_info: Optional[str] = None

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    street: Optional[str] = None
    building: Optional[str] = None
    city: Optional[str] = None
    additional_info: Optional[str] = None

class ChangePasswordInput(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)

class ContactInput(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr
    subject: str = Field(min_length=1)
    message: str = Field(min_length=1)

class ShippingAddress(BaseModel):
    full_name: str = Field(min_length=1)
    phone: Optional[str] = None
    street: str = Field(min_length=1)
    building: Optional[str] = None
    city: str = Field(min_length=1)
    additional_info: Optional[str] = None

class OrderCreate(BaseModel):
    album_id: str
    quantity: int = Field(default=1, ge=1, le=20)
    shipping_address: ShippingAddress

# Fixed page-count tiers the user picks from at album creation. A "custom"
# page count (not one of these) is priced at the nearest lower tier plus a
# per-page surcharge — see compute_order_price_cents.
PAGE_TIERS = [24, 50, 100, 150, 250]

# Price by format AND page tier, in cents — server-side only, the client
# never gets to set its own price. These are PLACEHOLDER values (Clara
# hasn't finalized real pricing with the printer yet) — adjust freely, this
# is the one place that needs to change once real prices are set.
ORDER_PRICE_CENTS = {
    "A5": {24: 2500, 50: 3500, 100: 5500, 150: 7500, 250: 11000},
    "A4": {24: 3500, 50: 4900, 100: 7900, 150: 10900, 250: 15900},
    "A3": {24: 5500, 50: 7500, 100: 11900, 150: 16900, 250: 24900},
}

# Per extra page beyond the nearest lower tier, in cents — also a
# placeholder until real per-page economics are confirmed.
OVERAGE_PER_PAGE_CENTS = {"A5": 30, "A4": 45, "A3": 70}

def compute_order_price_cents(size: str, target_pages: int) -> int:
    size = size if size in ORDER_PRICE_CENTS else "A4"
    tier_prices = ORDER_PRICE_CENTS[size]
    target_pages = max(1, int(target_pages or PAGE_TIERS[0]))
    if target_pages in tier_prices:
        return tier_prices[target_pages]
    lower_tiers = [t for t in PAGE_TIERS if t <= target_pages]
    base_tier = max(lower_tiers) if lower_tiers else min(PAGE_TIERS)
    extra_pages = max(0, target_pages - base_tier)
    return tier_prices[base_tier] + extra_pages * OVERAGE_PER_PAGE_CENTS[size]

ORDER_STATUSES = ["pending_payment", "paid", "processing", "printing", "shipped", "delivered", "cancelled"]

class AuthResponse(BaseModel):
    token: str
    user: UserOut

class ForgotPasswordInput(BaseModel):
    email: EmailStr

class ResetPasswordInput(BaseModel):
    token: str
    new_password: str = Field(min_length=6)

class GoogleAuthInput(BaseModel):
    credential: str  # ID token from Google Identity Services

class AppleAuthInput(BaseModel):
    id_token: str
    name: Optional[str] = None  # Apple only ever sends the name on first authorization

class AlbumCreate(BaseModel):
    title: str = "Untitled"
    country: str = ""
    year: int = Field(default_factory=lambda: datetime.now().year)
    cover_template_id: str = "default"
    cover: Optional[Dict[str, Any]] = None
    size: str = "A4"  # A3, A4 or A5
    orientation: str = "portrait"  # portrait or landscape
    target_pages: int = 50  # one of PAGE_TIERS, or any custom page count

class AlbumUpdate(BaseModel):
    title: Optional[str] = None
    country: Optional[str] = None
    year: Optional[int] = None
    cover_template_id: Optional[str] = None
    size: Optional[str] = None
    orientation: Optional[str] = None
    target_pages: Optional[int] = None
    pages: Optional[List[Dict[str, Any]]] = None
    status: Optional[str] = None
    cover_image_path: Optional[str] = None
    cover: Optional[Dict[str, Any]] = None

# ---------- Startup ----------
@app.on_event("startup")
async def startup():
    init_storage()
    # Create indexes
    await db.users.create_index("email", unique=True)
    await db.albums.create_index("user_id")
    await db.photos.create_index("album_id")
    await db.orders.create_index("user_id")
    logger.info("Startup complete")

@app.on_event("shutdown")
async def shutdown():
    client.close()

# ---------- Auth Routes ----------
@api_router.post("/auth/signup", response_model=AuthResponse)
async def signup(data: SignupInput):
    existing = await db.users.find_one({"email": data.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")
    user_id = str(uuid.uuid4())
    user_doc = {
        "id": user_id,
        "email": data.email.lower(),
        "password_hash": hash_password(data.password),
        "name": data.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user_doc)
    token = create_token(user_id)
    return AuthResponse(token=token, user=UserOut(id=user_id, email=data.email.lower(), name=data.name))

@api_router.post("/auth/login", response_model=AuthResponse)
async def login(data: LoginInput):
    user = await db.users.find_one({"email": data.email.lower()})
    if not user or not user.get("password_hash") or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    token = create_token(user["id"])
    return AuthResponse(token=token, user=UserOut(id=user["id"], email=user["email"], name=user["name"]))

@api_router.post("/auth/forgot-password")
async def forgot_password(data: ForgotPasswordInput):
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

@api_router.post("/auth/reset-password")
async def reset_password(data: ResetPasswordInput):
    user = await db.users.find_one({"reset_token": data.token})
    if not user:
        raise HTTPException(status_code=400, detail="Lien de réinitialisation invalide ou expiré")
    expires = user.get("reset_token_expires")
    if not expires or datetime.fromisoformat(expires) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Lien de réinitialisation invalide ou expiré")
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": hash_password(data.new_password)}, "$unset": {"reset_token": "", "reset_token_expires": ""}},
    )
    return {"message": "Mot de passe mis à jour"}

@api_router.post("/auth/google", response_model=AuthResponse)
async def google_auth(data: GoogleAuthInput):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="La connexion Google n'est pas configurée sur ce serveur (GOOGLE_CLIENT_ID manquant)")
    try:
        idinfo = google_id_token.verify_oauth2_token(data.credential, google_requests.Request(), GOOGLE_CLIENT_ID)
    except Exception as e:
        logger.error(f"Jeton Google invalide : {e}")
        raise HTTPException(status_code=401, detail="Jeton Google invalide")
    email = idinfo.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Impossible de récupérer l'email du compte Google")
    user = await upsert_oauth_user(email, idinfo.get("name"), "google")
    token = create_token(user["id"])
    return AuthResponse(token=token, user=UserOut(id=user["id"], email=user["email"], name=user["name"]))

@api_router.post("/auth/apple", response_model=AuthResponse)
async def apple_auth(data: AppleAuthInput):
    if not APPLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="La connexion Apple n'est pas configurée sur ce serveur (APPLE_CLIENT_ID manquant)")
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
        raise HTTPException(status_code=401, detail="Jeton Apple invalide")
    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Impossible de récupérer l'email du compte Apple")
    user = await upsert_oauth_user(email, data.name, "apple")
    token = create_token(user["id"])
    return AuthResponse(token=token, user=UserOut(id=user["id"], email=user["email"], name=user["name"]))

@api_router.get("/auth/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user)):
    return UserOut(
        id=user["id"], email=user["email"], name=user["name"],
        phone=user.get("phone"), street=user.get("street"),
        building=user.get("building"), city=user.get("city"),
        additional_info=user.get("additional_info"),
    )

@api_router.put("/auth/me", response_model=UserOut)
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

@api_router.put("/auth/password")
async def change_password(data: ChangePasswordInput, user: dict = Depends(get_current_user)):
    full_user = await db.users.find_one({"id": user["id"]})
    if not full_user or not full_user.get("password_hash") or not verify_password(data.current_password, full_user["password_hash"]):
        raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect")
    await db.users.update_one({"id": user["id"]}, {"$set": {"password_hash": hash_password(data.new_password)}})
    return {"message": "Mot de passe mis à jour"}

@api_router.post("/contact")
async def submit_contact(data: ContactInput):
    contact_id = str(uuid.uuid4())
    doc = {
        "id": contact_id,
        "name": data.name,
        "email": data.email.lower(),
        "subject": data.subject,
        "message": data.message,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.contact_messages.insert_one(doc)
    # Notify the team inbox if one is configured; never fails the request if
    # email sending isn't set up (already logged by send_email in that case).
    support_email = os.environ.get("SUPPORT_EMAIL")
    if support_email:
        send_email(
            support_email,
            f"[Contact] {data.subject}",
            f"From: {data.name} <{data.email}>\n\n{data.message}",
        )
    return {"message": "Message envoyé, nous vous répondrons rapidement."}

# ---------- Album Routes ----------
def make_title_page(title: str) -> dict:
    """The first interior page every album starts with — right after the
    cover, always right-hand (the left page of that spread stays blank), and
    pre-filled with the album's title plus a friendly hint. The user is free
    to add or remove anything on it afterward, hint included."""
    return {
        "id": str(uuid.uuid4()),
        "layout": "title_page",
        "items": [
            {
                "id": str(uuid.uuid4()),
                "type": "text",
                "content": title or "Untitled",
                "x": 0.1,
                "y": 0.38,
                "w": 0.8,
                "h": 0.16,
                "font": "'Baloo 2', sans-serif",
                "font_weight": "800",
                "font_size": 36,
                "color": "#1A1A17",
            },
            {
                "id": str(uuid.uuid4()),
                "type": "text",
                "content": "This is your first page — make it yours. Add photos, text, or anything else you'd like.",
                "x": 0.15,
                "y": 0.56,
                "w": 0.7,
                "h": 0.12,
                "font": "'Manrope', sans-serif",
                "font_weight": "400",
                "font_style": "italic",
                "font_size": 14,
                "color": "#8A8A82",
                "text_align": "center",
            },
        ],
    }

@api_router.post("/albums")
async def create_album(data: AlbumCreate, user: dict = Depends(get_current_user)):
    album_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    album = {
        "id": album_id,
        "user_id": user["id"],
        "title": data.title,
        "country": data.country,
        "year": data.year,
        "cover_template_id": data.cover_template_id,
        "size": data.size,
        "orientation": data.orientation,
        "target_pages": data.target_pages,
        "status": "draft",
        "pages": [make_title_page(data.title)],
        "cover_image_path": None,
        "cover": data.cover or {},
        "created_at": now,
        "updated_at": now,
    }
    await db.albums.insert_one(album)
    album.pop("_id", None)
    return album

@api_router.get("/albums")
async def list_albums(user: dict = Depends(get_current_user)):
    cursor = db.albums.find({"user_id": user["id"]}, {"_id": 0}).sort("updated_at", -1)
    albums = await cursor.to_list(500)
    ordered_ids = set(await db.orders.distinct("album_id", {"user_id": user["id"]}))
    now = datetime.now(timezone.utc)
    for a in albums:
        a["is_ordered"] = a["id"] in ordered_ids
        a["days_until_deletion"] = None
        if not a["is_ordered"] and a.get("created_at"):
            try:
                created = datetime.fromisoformat(a["created_at"])
                deadline = created + timedelta(days=DRAFT_ALBUM_RETENTION_DAYS)
                a["days_until_deletion"] = max(0, (deadline - now).days)
            except (ValueError, TypeError):
                pass
    return albums

def _json_safe(value):
    """Recursively replaces any NaN/Infinity float (not valid JSON, but a
    valid Python float that can end up stored from a numeric computation
    gone wrong) with 0, so a single bad value can't make an entire API
    response fail to serialize. Fixes already-affected records on read,
    without needing a manual database cleanup."""
    if isinstance(value, float):
        return value if math.isfinite(value) else 0
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value

@api_router.get("/albums/{album_id}")
async def get_album(album_id: str, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]}, {"_id": 0})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")
    # Also include photos
    photos = await db.photos.find({"album_id": album_id}, {"_id": 0}).to_list(1000)
    album["photos"] = _json_safe(photos)
    return album

@api_router.patch("/albums/{album_id}")
async def update_album(album_id: str, data: AlbumUpdate, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")
    update = {k: v for k, v in data.model_dump(exclude_none=True).items()}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.albums.update_one({"id": album_id}, {"$set": update})
    updated = await db.albums.find_one({"id": album_id}, {"_id": 0})
    return updated

@api_router.delete("/albums/{album_id}")
async def delete_album(album_id: str, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        return {"deleted": 0}

    was_ordered = await db.orders.find_one({"album_id": album_id}) is not None
    if was_ordered:
        # An order is a paying customer's record — never removable via this
        # endpoint, regardless of what the UI does or doesn't show. Matches
        # the 30-day draft purge's same rule (see cleanup_expired_albums).
        raise HTTPException(status_code=403, detail="Impossible de supprimer un album déjà commandé")

    photos = await db.photos.find({"album_id": album_id, "is_deleted": False}, {"_id": 0}).to_list(5000)
    for p in photos:
        delete_object(p.get("storage_path"))
        delete_object(p.get("thumbnail_path"))
        delete_object(p.get("medium_path"))
    delete_object(album.get("cover_image_path"))

    result = await db.albums.delete_one({"id": album_id, "user_id": user["id"]})
    await db.photos.update_many({"album_id": album_id}, {"$set": {"is_deleted": True}})
    return {"deleted": result.deleted_count}

# ---------- Photo Upload ----------
ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp"}

# A phone photo is often far larger than any of our page sizes need at
# print quality (300 DPI) — even our biggest format, A3, only needs
# ~3508x4961px (see pageDimsMm equivalent on the frontend). 5000px keeps a
# comfortable margin above that while cutting the excess most cameras
# capture well beyond what a printed page can show, saving real storage
# with no visible loss at print time.
MAX_STORED_DIMENSION_PX = 5000

def _store_image_with_thumbnail(path: str, data: bytes, content_type: str):
    """Uploads a print-quality (but not necessarily full-original-resolution)
    version of the image, then a best-effort 300x300 JPEG thumbnail alongside
    it (same path with _thumb.jpg instead of the original extension).
    Returns (upload_result, thumbnail_path_or_None, width_or_None,
    height_or_None). Shared by every place that stores an image + its
    thumbnail — regular photos, cover images, cover assets."""
    img_w, img_h = None, None
    thumb_path = None
    store_data, store_content_type = data, content_type
    try:
        with Image.open(BytesIO(data)) as _probe:
            orig_w, orig_h = _probe.size
            if max(orig_w, orig_h) > MAX_STORED_DIMENSION_PX:
                scaled = _probe.copy()
                scaled.thumbnail((MAX_STORED_DIMENSION_PX, MAX_STORED_DIMENSION_PX), Image.LANCZOS)
                out_buf = BytesIO()
                save_kwargs = {"quality": 92} if (_probe.format or "").upper() == "JPEG" else {}
                scaled.save(out_buf, format=_probe.format or "JPEG", **save_kwargs)
                store_data = out_buf.getvalue()
                img_w, img_h = scaled.size
            else:
                img_w, img_h = orig_w, orig_h
    except Exception as e:
        logger.debug(f"Impossible de redimensionner l'image à l'upload (on garde l'originale) : {e}")

    result = put_object(path, store_data, store_content_type)
    try:
        with Image.open(BytesIO(store_data)) as _probe:
            # For JPEGs, this tells the decoder to decode directly at
            # roughly this size instead of full resolution — a real
            # decode-time memory saving, not just a resize after the fact.
            # No-op (safely ignored) for PNG/WEBP.
            _probe.draft("RGB", (300, 300))
            thumb = _probe.convert("RGB") if _probe.mode not in ("RGB", "L") else _probe.copy()
            thumb.thumbnail((300, 300), Image.LANCZOS)
            thumb_buf = BytesIO()
            thumb.save(thumb_buf, format="JPEG", quality=82)
            thumb_path_candidate = path.rsplit(".", 1)[0] + "_thumb.jpg"
            put_object(thumb_path_candidate, thumb_buf.getvalue(), "image/jpeg")
            thumb_path = thumb_path_candidate
    except Exception as e:
        logger.debug(f"Impossible de générer la vignette (fallback sur l'original): {e}")
    return result, thumb_path, img_w, img_h

# Sharp enough to fill an on-screen flipbook page without looking soft,
# while staying much lighter than the up-to-5000px print original —
# generated on demand (see get_photo_image) rather than at upload time, so
# creating a big album never pays this cost for photos nobody ends up
# actually scrolling to.
MEDIUM_MAX_DIMENSION_PX = 1200

def _generate_medium_variant(photo: dict):
    """Resizes a photo's already-stored print-quality version down to the
    flipbook-viewing size, uploads it to R2 alongside the original and
    thumbnail, and returns (r2_path, jpeg_bytes) so the caller can serve it
    immediately without a second round-trip to R2. Returns (None, None) on
    any failure — the caller falls back to the thumbnail rather than
    erroring the whole page."""
    try:
        data, _ = get_object(photo["storage_path"])
        with Image.open(BytesIO(data)) as img:
            img = img.convert("RGB") if img.mode not in ("RGB", "L") else img.copy()
            img.thumbnail((MEDIUM_MAX_DIMENSION_PX, MEDIUM_MAX_DIMENSION_PX), Image.LANCZOS)
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=88)
            medium_bytes = buf.getvalue()
        medium_path = photo["storage_path"].rsplit(".", 1)[0] + "_medium.jpg"
        put_object(medium_path, medium_bytes, "image/jpeg")
        return medium_path, medium_bytes
    except Exception as e:
        logger.error(f"Impossible de générer la variante 'medium' pour la photo {photo.get('id')}: {e}")
        return None, None

def _process_photo_sync(data: bytes, content_type: str, filename: str, user_id: str, album_id: str) -> dict:
    """All the CPU/disk-bound work for one photo — EXIF, thumbnail
    generation, perceptual hash, and the two disk writes. Deliberately a
    plain synchronous function (no async, no awaits) so it can run in a
    thread executor: none of this benefits from asyncio on its own, and
    running it inline on the event loop was blocking every other request
    (and every other photo in the same batch) for its entire duration."""
    ext = (filename or "img.jpg").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"
    photo_id = str(uuid.uuid4())
    path = f"{APP_NAME}/users/{user_id}/albums/{album_id}/{photo_id}.{ext}"
    exif_info = extract_exif_info(data)
    result, thumb_path, img_w, img_h = _store_image_with_thumbnail(path, data, content_type)

    return {
        "photo_id": photo_id,
        "storage_path": result["path"],
        "thumbnail_path": thumb_path,
        "size": result.get("size", len(data)),
        "width": img_w,
        "height": img_h,
        "taken_at": exif_info["taken_at"],
        "gps_lat": exif_info["gps_lat"],
        "gps_lng": exif_info["gps_lng"],
        "phash": _ahash_to_str(compute_ahash(data)),
    }

async def _store_new_photo(album_id: str, user_id: str, filename: str, content_type: str, data: bytes) -> Optional[dict]:
    """Shared logic to persist one photo (bytes already in hand) as a Photo
    document — used by the normal upload endpoint, the phone QR upload, and
    the Google Photos import, so all three go through the exact same
    EXIF/hash/storage pipeline."""
    if content_type not in ALLOWED_MIME:
        return None
    if len(data) == 0:
        return None
    try:
        loop = asyncio.get_event_loop()
        processed = await loop.run_in_executor(None, _process_photo_sync, data, content_type, filename, user_id, album_id)
    except Exception as e:
        logger.error(f"Upload failed for {filename}: {e}")
        return None
    photo_doc = {
        "id": processed["photo_id"],
        "album_id": album_id,
        "user_id": user_id,
        "storage_path": processed["storage_path"],
        "thumbnail_path": processed["thumbnail_path"],
        "original_filename": filename,
        "content_type": content_type,
        "size": processed["size"],
        "width": processed["width"],
        "height": processed["height"],
        "ai_score": None,
        "ai_description": None,
        "ai_group": None,
        "ai_is_reject": False,
        "ai_focal_x": 0.5,
        "ai_focal_y": 0.5,
        "taken_at": processed["taken_at"],
        "gps_lat": processed["gps_lat"],
        "gps_lng": processed["gps_lng"],
        "phash": processed["phash"],
        "is_selected": True,
        "is_duplicate": False,
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.photos.insert_one(photo_doc)
    photo_doc.pop("_id", None)
    return photo_doc

async def _store_many_photos(album_id: str, user_id: str, files: List[UploadFile]) -> List[dict]:
    """Reads then stores a batch of uploaded files concurrently (bounded by
    UPLOAD_CONCURRENCY), skipping any that fail validation or processing.
    Shared by every endpoint that accepts photo uploads. Files are read here
    (must happen on the main loop — UploadFile isn't safe to touch from a
    worker thread), but everything CPU/disk-bound after that runs
    concurrently, bounded so a huge batch doesn't spawn hundreds of threads
    at once."""
    file_bytes = [(f.filename, f.content_type or "image/jpeg", await f.read()) for f in files]
    semaphore = asyncio.Semaphore(UPLOAD_CONCURRENCY)

    async def store_one(filename, content_type, data):
        async with semaphore:
            return await _store_new_photo(album_id, user_id, filename, content_type, data)

    results = await asyncio.gather(*(store_one(fn, ct, d) for fn, ct, d in file_bytes))
    return [p for p in results if p]

@api_router.post("/albums/{album_id}/photos")
async def upload_photos(
    album_id: str,
    files: List[UploadFile] = File(...),
    user: dict = Depends(get_current_user),
):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")
    uploaded = await _store_many_photos(album_id, user["id"], files)
    return {"uploaded": len(uploaded), "photos": uploaded}

# ---------- Mobile upload (QR code) ----------
MOBILE_UPLOAD_SESSION_HOURS = 1
_mobile_sessions: Dict[str, dict] = {}  # token -> {album_id, user_id, expires}

class MobileUploadSessionOut(BaseModel):
    token: str
    upload_url: str
    expires_at: str

@api_router.post("/albums/{album_id}/mobile-upload-session", response_model=MobileUploadSessionOut)
async def create_mobile_upload_session(album_id: str, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")
    token = str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(hours=MOBILE_UPLOAD_SESSION_HOURS)
    _mobile_sessions[token] = {"album_id": album_id, "user_id": user["id"], "expires": expires}
    return MobileUploadSessionOut(
        token=token,
        upload_url=f"{FRONTEND_URL}/mobile-upload/{token}",
        expires_at=expires.isoformat(),
    )

def _get_mobile_session(token: str) -> dict:
    session = _mobile_sessions.get(token)
    if not session or session["expires"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Ce lien a expiré ou est invalide")
    return session

@api_router.get("/mobile-upload/{token}/info")
async def mobile_upload_info(token: str):
    session = _get_mobile_session(token)
    album = await db.albums.find_one({"id": session["album_id"]}, {"_id": 0, "title": 1})
    return {"album_title": (album or {}).get("title", "Album"), "expires_at": session["expires"].isoformat()}

@api_router.post("/mobile-upload/{token}/photos")
async def mobile_upload_photos(token: str, background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)):
    session = _get_mobile_session(token)
    uploaded = await _store_many_photos(session["album_id"], session["user_id"], files)

    if uploaded:
        album = await db.albums.find_one({"id": session["album_id"]}, {"_id": 0, "status": 1})
        # If the album has already been through its first AI pass (i.e. this
        # is "Add more photos" from the editor, not the initial creation
        # wizard), curate and append pages for these right away. During the
        # wizard, photos just land in the pool until "Start AI" is clicked.
        if album and album.get("status") == "ready":
            await db.albums.update_one({"id": session["album_id"]}, {"$set": {"status": "processing"}})
            background_tasks.add_task(
                run_ai_processing_incremental, session["album_id"], session["user_id"], [p["id"] for p in uploaded]
            )
    return {"uploaded": len(uploaded)}

# ---------- Google Photos import (Photos Picker API) ----------
class GooglePhotosImportInput(BaseModel):
    access_token: str
    items: List[Dict[str, Any]]  # one batch of raw mediaItems from the Photos Picker API — the frontend now fetches the full selection itself and sends it here in small batches (same shape as regular multi-photo upload), instead of handing over a session_id and making the backend do everything (originals, potentially hundreds of them) inside a single background task. A background task only gets a fraction of its normal CPU once Cloud Run's request-based billing considers the request "done" — which made large imports far slower than an equivalent active request. Small batches processed as ordinary active requests never hit that throttling, exactly like regular device uploads already didn't.

@api_router.post("/albums/{album_id}/import/google-photos")
async def import_google_photos(album_id: str, data: GooglePhotosImportInput, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")

    headers = {"Authorization": f"Bearer {data.access_token}"}
    # Bounded lower than UPLOAD_CONCURRENCY (a separate constant, see near
    # the top of the file) — hammering Google's own servers with many
    # simultaneous connections is what caused SSLEOFError/"Max retries
    # exceeded" drops, so Google Photos downloads specifically stay
    # bounded lower regardless of how high UPLOAD_CONCURRENCY is set for
    # the unrelated device-upload path.
    semaphore = asyncio.Semaphore(GOOGLE_PHOTOS_CONCURRENCY)
    loop = asyncio.get_event_loop()

    async def fetch_one(item):
        media_file = item.get("mediaFile", {})
        base_url = media_file.get("baseUrl")
        filename = media_file.get("filename", "photo.jpg")
        if not base_url:
            return None
        # Google's servers occasionally drop the connection under
        # concurrent load (SSLEOFError / "Max retries exceeded") — this is
        # a transient network hiccup, not a real failure, and a retry
        # almost always succeeds. The semaphore is only held during the
        # actual attempt, never during the backoff sleep, so one failing,
        # retrying photo doesn't starve every other photo waiting for that
        # slot.
        last_error = None
        for attempt in range(3):
            async with semaphore:
                try:
                    img_resp = await loop.run_in_executor(
                        None, lambda: requests.get(f"{base_url}=d", headers=headers, timeout=20)
                    )
                    if img_resp.status_code != 200:
                        return None
                    content_type = img_resp.headers.get("Content-Type", "image/jpeg")
                    return await _store_new_photo(album_id, user["id"], filename, content_type, img_resp.content)
                except Exception as e:
                    last_error = e
            if attempt < 2:
                await asyncio.sleep(1.5 * (attempt + 1))  # 1.5s, then 3s — outside the semaphore
        logger.error(f"Échec du téléchargement d'une photo Google Photos ({filename}) après 3 tentatives : {last_error}")
        return None

    results = await asyncio.gather(*(fetch_one(it) for it in data.items))
    uploaded = [p for p in results if p]

    # Mirrors the regular "add more photos" behavior exactly: only kick off
    # AI processing here if the album had already been through its first
    # AI pass before (the "editor" / add-more-later case). During the
    # creation wizard the album is still a fresh draft — photos just land
    # in the pool, and the wizard's own "Start AI" step processes
    # everything (this batch plus every other one) together, once.
    if uploaded and album.get("status") == "ready":
        await db.albums.update_one({"id": album_id}, {"$set": {"status": "processing"}})
        # Awaited, not background-tasked — same throttling issue as
        # /albums/{id}/process (see its comment). Each batch is already
        # small (~20 photos), so this stays quick even run inline.
        await run_ai_processing_incremental(album_id, user["id"], [p["id"] for p in uploaded])

    return {"uploaded": len(uploaded), "total": len(data.items)}

@api_router.get("/photos/{photo_id}/image")
async def get_photo_image(photo_id: str, auth: str = Query(None), authorization: str = Header(None), variant: str = Query("thumb")):
    # Support both header and query auth (for <img> tags)
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    elif auth:
        token = auth
    user_id = decode_token(token) if token else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    photo = await db.photos.find_one({"id": photo_id, "user_id": user_id, "is_deleted": False})
    if not photo:
        raise HTTPException(status_code=404, detail="Photo introuvable")
    # "thumb" (small grids — the photo tray, upload picker) keeps browsing
    # fast; "medium" (the flipbook / editor page view) is sharp enough for
    # a full on-screen page without the cost of the full original;
    # "original" (used only by the PDF print page) always gets the
    # full-resolution file, since print quality must never be compromised.
    path = photo["storage_path"]
    served_content_type = photo.get("content_type")
    if variant == "thumb" and photo.get("thumbnail_path"):
        path = photo["thumbnail_path"]
        served_content_type = "image/jpeg"
    elif variant == "medium":
        if photo.get("medium_path"):
            # Already generated by an earlier request — no resizing work,
            # just serve the cached file like any other variant.
            path = photo["medium_path"]
            served_content_type = "image/jpeg"
        else:
            # First time this photo's medium size has ever been requested.
            # Generated here, on demand, rather than at upload time — most
            # of a large album's photos are never actually scrolled to in
            # the flipbook, so generating this for every photo up front
            # would waste time on pages nobody looks at. Cached to R2
            # afterwards so every subsequent view (this person or anyone
            # else) is an ordinary fast fetch, not a repeat resize.
            loop = asyncio.get_event_loop()
            medium_path, medium_bytes = await loop.run_in_executor(None, _generate_medium_variant, photo)
            if medium_path:
                await db.photos.update_one({"id": photo_id}, {"$set": {"medium_path": medium_path}})
                path, served_content_type = medium_path, "image/jpeg"
                data = medium_bytes
                return Response(content=data, media_type=served_content_type, headers={"Cache-Control": "private, max-age=31536000, immutable"})
            # Fell through — resizing failed for some reason; serve the
            # thumbnail rather than the (much heavier) original as a safe
            # fallback so the page still renders something reasonable.
            if photo.get("thumbnail_path"):
                path, served_content_type = photo["thumbnail_path"], "image/jpeg"
    data, ctype = get_object(path)
    return Response( content=data, media_type=served_content_type or ctype, headers={"Cache-Control": "private, max-age=31536000, immutable"}, )

# ---------- Cover image upload ----------
@api_router.post("/albums/{album_id}/cover-image")
async def upload_cover_image(
    album_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")
    content_type = file.content_type or "image/jpeg"
    if content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Format d'image non supporté")
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Fichier vide")
    ext = (file.filename or "cover.jpg").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"
    path = f"{APP_NAME}/users/{user['id']}/albums/{album_id}/cover-{uuid.uuid4()}.{ext}"
    loop = asyncio.get_event_loop()
    result, thumb_path, _, _ = await loop.run_in_executor(None, _store_image_with_thumbnail, path, data, content_type)
    await db.albums.update_one(
        {"id": album_id},
        {"$set": {
            "cover_image_path": result["path"],
            "cover_image_thumbnail_path": thumb_path,
            "cover_image_content_type": content_type,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )
    return {"cover_image_path": result["path"]}

@api_router.delete("/albums/{album_id}/cover-image")
async def remove_cover_image(album_id: str, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")
    await db.albums.update_one(
        {"id": album_id},
        {"$set": {"cover_image_path": None, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"ok": True}

@api_router.get("/albums/{album_id}/cover-image")
async def get_cover_image(album_id: str, auth: str = Query(None), authorization: str = Header(None), variant: str = Query("thumb")):
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    elif auth:
        token = auth
    user_id = decode_token(token) if token else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    album = await db.albums.find_one({"id": album_id, "user_id": user_id})
    if not album or not album.get("cover_image_path"):
        raise HTTPException(status_code=404, detail="Aucune couverture personnalisée")
    path = album["cover_image_path"]
    served_content_type = album.get("cover_image_content_type")
    if variant == "thumb" and album.get("cover_image_thumbnail_path"):
        path = album["cover_image_thumbnail_path"]
        served_content_type = "image/jpeg"
    data, ctype = get_object(path)
    return Response(content=data, media_type=served_content_type or ctype)

# ---------- Cover element assets (logo / added images on the cover) ----------
@api_router.post("/albums/{album_id}/cover-assets")
async def upload_cover_asset(album_id: str, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")
    content_type = file.content_type or "image/png"
    if content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Format d'image non supporté")
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Fichier vide")
    ext = (file.filename or "asset.png").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "png"
    asset_id = str(uuid.uuid4())
    path = f"{APP_NAME}/users/{user['id']}/albums/{album_id}/cover-assets/{asset_id}.{ext}"
    loop = asyncio.get_event_loop()
    result, thumb_path, _, _ = await loop.run_in_executor(None, _store_image_with_thumbnail, path, data, content_type)
    return {"storage_path": result["path"], "thumbnail_path": thumb_path}

@api_router.get("/cover-assets/image")
async def get_cover_asset_image(path: str = Query(...), auth: str = Query(None), authorization: str = Header(None), variant: str = Query("thumb")):
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    elif auth:
        token = auth
    user_id = decode_token(token) if token else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Safety: only serve assets that belong to the requesting user
    if f"/users/{user_id}/" not in path:
        raise HTTPException(status_code=403, detail="Accès refusé")
    served_path = path
    served_content_type = None
    if variant == "thumb" and not path.endswith("_thumb.jpg"):
        candidate = path.rsplit(".", 1)[0] + "_thumb.jpg"
        try:
            data, ctype = get_object(candidate)
            return Response(content=data, media_type="image/jpeg")
        except Exception:
            pass  # no thumbnail on disk (asset predates this change, or generation failed) — fall back to original
    data, ctype = get_object(served_path)
    return Response(content=data, media_type=served_content_type or ctype)


# ---------- AI Processing ----------
def _rational_to_float(r):
    try:
        return float(r)
    except Exception:
        try:
            return r[0] / r[1]
        except Exception:
            return 0.0


def extract_exif_info(data: bytes) -> dict:
    """Best-effort extraction of capture date and GPS coordinates from EXIF.
    Returns {"taken_at": iso_str|None, "gps_lat": float|None, "gps_lng": float|None}.
    Missing/corrupt EXIF is common (screenshots, edited photos) — fails silently."""
    info = {"taken_at": None, "gps_lat": None, "gps_lng": None}
    try:
        img = Image.open(BytesIO(data))
        exif = img.getexif()
        if not exif:
            return info
        tags = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
        exif_ifd = exif.get_ifd(0x8769) if hasattr(exif, "get_ifd") else {}
        exif_ifd_tags = {ExifTags.TAGS.get(k, k): v for k, v in (exif_ifd or {}).items()}
        raw_dt = tags.get("DateTime") or exif_ifd_tags.get("DateTimeOriginal") or exif_ifd_tags.get("DateTimeDigitized")
        if raw_dt:
            try:
                info["taken_at"] = datetime.strptime(raw_dt, "%Y:%m:%d %H:%M:%S").isoformat()
            except Exception:
                pass
        gps_ifd = exif.get_ifd(0x8825) if hasattr(exif, "get_ifd") else {}
        if gps_ifd:
            gps = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}
            lat, lat_ref = gps.get("GPSLatitude"), gps.get("GPSLatitudeRef")
            lng, lng_ref = gps.get("GPSLongitude"), gps.get("GPSLongitudeRef")
            if lat and lng:
                lat_val = _rational_to_float(lat[0]) + _rational_to_float(lat[1]) / 60 + _rational_to_float(lat[2]) / 3600
                lng_val = _rational_to_float(lng[0]) + _rational_to_float(lng[1]) / 60 + _rational_to_float(lng[2]) / 3600
                if lat_ref == "S":
                    lat_val = -lat_val
                if lng_ref == "W":
                    lng_val = -lng_val
                info["gps_lat"] = round(lat_val, 6)
                info["gps_lng"] = round(lng_val, 6)
    except Exception as e:
        logger.debug(f"EXIF extraction failed: {e}")
    return info


def compute_ahash(data: bytes) -> Optional[int]:
    """64-bit average hash (aHash) for near-duplicate detection. Two photos
    with a small Hamming distance between hashes are visually near-identical
    (same burst, same framing) — used to find real duplicates deterministically,
    on top of what the AI itself flags."""
    try:
        img = Image.open(BytesIO(data))
        img.draft("L", (32, 32))  # decode near the target size directly, not full-resolution
        img = img.convert("L").resize((8, 8), Image.LANCZOS)
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        bits = "".join("1" if p >= avg else "0" for p in pixels)
        return int(bits, 2)
    except Exception as e:
        logger.debug(f"Hash computation failed: {e}")
        return None


def _ahash_to_str(h: Optional[int]) -> Optional[str]:
    """MongoDB/BSON only supports signed 64-bit ints — our 64-bit average
    hash is unsigned and can exceed that range, so it's stored as a fixed
    16-char hex string instead."""
    return f"{h:016x}" if h is not None else None


def compute_sharpness(data: bytes) -> float:
    """Cheap, no-AI focus/sharpness estimate (Laplacian variance on a small
    grayscale version) — used to pick the best frame out of a burst/cluster
    of near-duplicates cheaply and locally, no external service call needed.
    Higher = sharper. Purely classical image processing, near-instant."""
    try:
        with Image.open(BytesIO(data)) as img:
            img.draft("L", (256, 256))
            small = img.convert("L").resize((256, 256), Image.LANCZOS)
            arr = np.asarray(small, dtype=np.float64)
            # Simple discrete Laplacian kernel (edge/detail response)
            lap = (
                -4 * arr
                + np.roll(arr, 1, axis=0) + np.roll(arr, -1, axis=0)
                + np.roll(arr, 1, axis=1) + np.roll(arr, -1, axis=1)
            )
            result = float(lap.var())
            if not math.isfinite(result):
                return 0.0
            return result
    except Exception:
        return 0.0

def hamming_distance(a, b) -> int:
    if a is None or b is None:
        return 64  # unknown hash → treat as "not the same photo"
    ai = int(a, 16) if isinstance(a, str) else a
    bi = int(b, 16) if isinstance(b, str) else b
    return bin(ai ^ bi).count("1")


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two GPS points, in kilometers."""
    from math import radians, sin, cos, sqrt, atan2
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def cluster_by_location(photos: List[dict], threshold_km: float = 1.5) -> List[List[dict]]:
    """Greedily groups photos taken close to each other (same venue / same
    stop on the trip) using their GPS coordinates. Each photo must already
    have gps_lat/gps_lng set."""
    clusters: List[dict] = []  # {"lat": float, "lng": float, "photos": [...]}
    for p in photos:
        placed = False
        for c in clusters:
            if haversine_km(p["gps_lat"], p["gps_lng"], c["lat"], c["lng"]) <= threshold_km:
                n = len(c["photos"]) + 1
                c["lat"] = (c["lat"] * (n - 1) + p["gps_lat"]) / n
                c["lng"] = (c["lng"] * (n - 1) + p["gps_lng"]) / n
                c["photos"].append(p)
                placed = True
                break
        if not placed:
            clusters.append({"lat": p["gps_lat"], "lng": p["gps_lng"], "photos": [p]})
    return [c["photos"] for c in clusters]


LAYOUT_PATTERN = ["single_full", "dual_vertical", "hero_strip", "single_centered", "quad_grid", "triptych", "dual_horizontal"]

def deterministic_layout(photos: List[dict], orientation: str, pattern_start_idx: int = 0) -> List[dict]:
    """Distribute photos across pages with varied layouts.
    Returns a list of pages (each with items containing photo refs and positions in normalized 0-1 coordinates).
    """
    M = 0.05  # Marge globale de 5%
    usable = 1.0 - (2 * M)  # Espace utile de 0.9 (90% de la page)

    layouts = {
        "single_full": [
            {"x": M, "y": M, "w": usable, "h": usable}
        ],
        "single_centered": [
            {"x": 0.15, "y": 0.15, "w": 0.7, "h": 0.7}
        ],
        "dual_horizontal": [
            {"x": M, "y": M, "w": usable, "h": (usable - 0.04) / 2},
            {"x": M, "y": M + (usable - 0.04) / 2 + 0.04, "w": usable, "h": (usable - 0.04) / 2},
        ],
        "dual_vertical": [
            {"x": M, "y": M, "w": (usable - 0.04) / 2, "h": usable},
            {"x": M + (usable - 0.04) / 2 + 0.04, "y": M, "w": (usable - 0.04) / 2, "h": usable},
        ],
        "triptych": [
            {"x": M, "y": M, "w": usable * 0.58, "h": usable},
            {"x": M + usable * 0.58 + 0.03, "y": M, "w": usable * 0.39, "h": (usable - 0.03) / 2},
            {"x": M + usable * 0.58 + 0.03, "y": M + (usable - 0.03) / 2 + 0.03, "w": usable * 0.39, "h": (usable - 0.03) / 2},
        ],
        "quad_grid": [
            {"x": M, "y": M, "w": (usable - 0.03) / 2, "h": (usable - 0.03) / 2},
            {"x": M + (usable - 0.03) / 2 + 0.03, "y": M, "w": (usable - 0.03) / 2, "h": (usable - 0.03) / 2},
            {"x": M, "y": M + (usable - 0.03) / 2 + 0.03, "w": (usable - 0.03) / 2, "h": (usable - 0.03) / 2},
            {"x": M + (usable - 0.03) / 2 + 0.03, "y": M + (usable - 0.03) / 2 + 0.03, "w": (usable - 0.03) / 2, "h": (usable - 0.03) / 2},
        ],
        "hero_strip": [
            {"x": M, "y": M, "w": usable, "h": usable * 0.62},
            {"x": M, "y": M + usable * 0.62 + 0.03, "w": (usable - 0.06) / 3, "h": usable * 0.35},
            {"x": M + (usable - 0.06) / 3 + 0.03, "y": M + usable * 0.62 + 0.03, "w": (usable - 0.06) / 3, "h": usable * 0.35},
            {"x": M + 2 * ((usable - 0.06) / 3 + 0.03), "y": M + usable * 0.62 + 0.03, "w": (usable - 0.06) / 3, "h": usable * 0.35},
        ],
    }

    # Alternate layouts to create diversity
    pattern = LAYOUT_PATTERN

    # A4/A5 share the same aspect ratio (ISO 216) — only orientation matters here.
    page_aspect_wh = 1.4142 if orientation == "landscape" else 0.7071

    def photo_aspect(p: dict) -> float:
        w, h = p.get("width"), p.get("height")
        if w and h and h > 0:
            return w / h
        return 1.0  # unknown dimensions → treat as neutral, no strong preference

    def best_slot_assignment(slots: List[dict], candidates: List[dict]) -> Dict[int, int]:
        """Greedily pairs each slot with whichever candidate photo's aspect
        ratio fits it best (smallest log-ratio mismatch), so a portrait photo
        doesn't end up forced into a wide landscape slot (and vice versa) —
        that mismatch is what causes heavy, awkward cropping."""
        import math
        slot_aspects = [(s["w"] / s["h"]) * page_aspect_wh for s in slots]
        remaining_slots = list(range(len(slots)))
        remaining_candidates = list(range(len(candidates)))
        assignment: Dict[int, int] = {}
        while remaining_slots and remaining_candidates:
            best = None
            for si in remaining_slots:
                for ci in remaining_candidates:
                    cost = abs(math.log(slot_aspects[si] / photo_aspect(candidates[ci])))
                    if best is None or cost < best[0]:
                        best = (cost, si, ci)
            _, si, ci = best
            assignment[si] = ci
            remaining_slots.remove(si)
            remaining_candidates.remove(ci)
        return assignment

    LOOKAHEAD_EXTRA = 4  # how many extra upcoming photos to consider per page, for better shape matches
    pages = []
    remaining = list(photos)
    p_idx = pattern_start_idx
    while remaining:
        layout_name = pattern[p_idx % len(pattern)]
        slots = layouts[layout_name]
        window_size = min(len(remaining), len(slots) + LOOKAHEAD_EXTRA)
        candidates = remaining[:window_size]
        assignment = best_slot_assignment(slots, candidates)
        if not assignment:
            break
        items = []
        for slot_idx, slot in enumerate(slots):
            if slot_idx not in assignment:
                continue
            photo = candidates[assignment[slot_idx]]
            items.append({
                "id": str(uuid.uuid4()),
                "type": "photo",
                "photo_id": photo["id"],
                "x": slot["x"],
                "y": slot["y"],
                "w": slot["w"],
                "h": slot["h"],
                "focal_x": photo.get("ai_focal_x", 0.5),
                "focal_y": photo.get("ai_focal_y", 0.5),
            })
        pages.append({
            "id": str(uuid.uuid4()),
            "layout": layout_name,
            "items": items,
        })
        # Drop the photos that were used (order-preserving) — the rest, including
        # any lookahead candidates that weren't picked this time, stay in the
        # queue for the next page in their original relative order.
        used_ids = {candidates[ci]["id"] for ci in assignment.values()}
        remaining = [p for p in remaining if p["id"] not in used_ids]
        p_idx += 1
    return pages

async def _curate_photos(new_photos: List[dict], existing_selected: Optional[List[dict]] = None) -> List[dict]:
    """Real duplicate/burst detection, fast local best-of-cluster selection,
    a classical sharpness quality gate on the survivors, and
    group/date/location sorting. When `existing_selected` is given
    (already-placed photos elsewhere in the album), new photos are also
    checked for duplicates against them — a new photo that matches
    something already in the album is dropped, and the pre-existing photo
    is left untouched either way. Returns (selected, stats) — selected is
    the final ordered list of NEW photos to lay out (existing photos are
    never included), stats is a dict of counts (total_in,
    duplicates_removed, low_sharpness_removed, selected) for diagnosing a
    surprising outcome after the fact."""
    existing_selected = existing_selected or []
    existing_ids = {e["id"] for e in existing_selected}

    # ---- 1. Real duplicate/burst detection (new photos vs each other AND
    # vs what's already in the album) — done BEFORE any AI call, using only
    # cheap local signals: perceptual similarity (phash) and how close
    # together in time the shots were taken. Photos taken close together in
    # time are almost certainly the same moment even if the framing/angle
    # drifted a bit (someone stepping sideways, a slightly different crop of
    # the same scene), so those get a looser similarity threshold; photos
    # with no timing signal (or taken far apart) need to look genuinely
    # closer to each other to be treated as the same shot. ----
    HASH_THRESHOLD = 8
    BURST_HASH_THRESHOLD = 20
    BURST_SECONDS = 45

    def _parse_taken_at(p):
        ts = p.get("taken_at")
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return None

    def _is_match(p, other):
        dist = hamming_distance(p.get("phash"), other.get("phash"))
        t1, t2 = _parse_taken_at(p), _parse_taken_at(other)
        if t1 and t2 and abs((t1 - t2).total_seconds()) <= BURST_SECONDS:
            return dist <= BURST_HASH_THRESHOLD
        return dist <= HASH_THRESHOLD

    clusters: List[List[dict]] = [[e] for e in existing_selected]
    for p in new_photos:
        placed = False
        for cluster in clusters:
            # Compare against every photo already in the cluster, not just
            # the first one added — a burst sequence can drift gradually
            # frame to frame, so the closest match may be a later member.
            if any(_is_match(p, member) for member in cluster):
                cluster.append(p)
                placed = True
                break
        if not placed:
            clusters.append([p])

    # Diagnostic counters — surfaced via curation_stats on the album, so a
    # surprising outcome (a lot of photos going in, few pages coming out)
    # can be traced to "mostly duplicates" vs "mostly failed the sharpness
    # gate" instead of guessing.
    duplicates_removed = 0
    low_sharpness_removed = 0

    # ---- 2. Pick a representative per cluster using a fast, local,
    # no-AI sharpness check — this is what lets us skip sending every burst
    # frame locally, no external AI call needed. ----
    loop = asyncio.get_event_loop()

    async def _sharpness_of(p):
        try:
            read_path = p.get("thumbnail_path") or p["storage_path"]
            data, _ = await loop.run_in_executor(None, get_object, read_path)
            return await loop.run_in_executor(None, compute_sharpness, data)
        except Exception:
            return 0.0

    representatives: List[dict] = []  # one per cluster that has at least one new photo
    rep_sharpness: Dict[str, float] = {}
    for cluster in clusters:
        new_in_cluster = [c for c in cluster if c["id"] not in existing_ids]
        if not new_in_cluster:
            continue  # cluster made only of pre-existing photos — nothing new here
        if cluster[0]["id"] in existing_ids:
            # An existing photo anchors this cluster — every new photo here
            # is a duplicate of it, so none of them need scoring at all.
            for d in new_in_cluster:
                await db.photos.update_one({"id": d["id"]}, {"$set": {"is_duplicate": True, "is_selected": False}})
            duplicates_removed += len(new_in_cluster)
            continue
        sharpness_scores = await asyncio.gather(*(_sharpness_of(p) for p in new_in_cluster))
        rep, rep_score = max(zip(new_in_cluster, sharpness_scores), key=lambda x: x[1])
        for d, score in zip(new_in_cluster, sharpness_scores):
            if d["id"] != rep["id"]:
                await db.photos.update_one({"id": d["id"]}, {"$set": {"is_duplicate": True, "is_selected": False}})
        duplicates_removed += len(new_in_cluster) - 1
        representatives.append(rep)
        rep_sharpness[rep["id"]] = rep_score

    # ---- 3. Quality gate — classical, no AI call. A genuinely broken shot
    # (severe motion blur, a finger over the lens, camera-shake) scores
    # dramatically lower on the same sharpness metric than a normal in-focus
    # photo, even accounting for scene-to-scene variation (a plain sky vs. a
    # detailed street scene) — this catches the clear failures without
    # needing semantic judgment of composition/expression, which is the
    # trade-off of not calling an AI model here. Deliberately conservative
    # (low threshold) so it only screens out unambiguous misses rather than
    # trying to rank "good" vs "great".
    #
    # NOTE: this fixed number was never calibrated against a real batch of
    # photos — a scene with naturally low local contrast (sky, water, flat
    # backgrounds) can score low on this metric even in perfect focus, so a
    # value this high risks rejecting plenty of genuinely fine photos, not
    # just broken ones. Lowered from 15.0 pending real before/after data
    # from curation_stats. ----
    SHARPNESS_FLOOR = 8.0
    selected = []
    for rep in representatives:
        score = rep_sharpness.get(rep["id"], 0.0)
        update = {
            "ai_score": score,
            "ai_is_reject": score < SHARPNESS_FLOOR,
            # No AI call means no suggested focal point — default to center,
            # same as any manually-added photo; the user can still drag to
            # reframe any photo in the editor same as always.
            "ai_focal_x": 0.5,
            "ai_focal_y": 0.5,
        }
        await db.photos.update_one({"id": rep["id"]}, {"$set": update})
        rep.update(update)
        if update["ai_is_reject"]:
            await db.photos.update_one({"id": rep["id"]}, {"$set": {"is_duplicate": True, "is_selected": False}})
            low_sharpness_removed += 1
        else:
            await db.photos.update_one({"id": rep["id"]}, {"$set": {"is_duplicate": False, "is_selected": True}})
            selected.append(rep)

    # ---- 4. Group & sort (place / date priority, same rules as the initial pass) ----
    with_gps = [p for p in selected if p.get("gps_lat") is not None and p.get("gps_lng") is not None]
    with_gps_ids = {p["id"] for p in with_gps}
    without_gps = [p for p in selected if p["id"] not in with_gps_ids]

    if len(with_gps) >= max(2, len(selected) * 0.3):
        location_groups = cluster_by_location(with_gps)
        for group in location_groups:
            group.sort(key=lambda x: x.get("taken_at") or "9999-12-31")

        def group_sort_key(group):
            dated = [p.get("taken_at") for p in group if p.get("taken_at")]
            return min(dated) if dated else "9999-12-31"

        location_groups.sort(key=group_sort_key)
        selected = [p for group in location_groups for p in group]
        without_gps.sort(key=lambda x: x.get("taken_at") or "9999-12-31")
        selected.extend(without_gps)
    else:
        dated = [p for p in selected if p.get("taken_at")]
        if len(dated) >= max(1, len(selected) * 0.5):
            selected.sort(key=lambda x: x.get("taken_at") or "9999-12-31")
        else:
            selected.sort(key=lambda x: (x.get("ai_group", "zzz"), -(x.get("ai_score") or 0)))

    stats = {
        "total_in": len(new_photos),
        "duplicates_removed": duplicates_removed,
        "low_sharpness_removed": low_sharpness_removed,
        "selected": len(selected),
    }
    return selected, stats


async def _trim_pages_to_target(pages: List[dict], target_pages: int) -> tuple:
    """Trims `pages` (title page included) down to at most target_pages —
    the real fix for the AI-generated layout drifting from whatever page
    tier the user paid for at album creation, since deterministic_layout
    otherwise just produces however many pages the selected photos happen
    to fill. Any photo that lands on a trimmed-off page is un-selected
    (not deleted outright — see _delete_unselected_photos for when the
    actual files get cleaned up, at order time) so it stops showing up
    anywhere in the app. Returns (trimmed_pages, fell_short) — fell_short
    is True when there weren't even enough good photos to reach the target,
    which the frontend can use to warn the person rather than silently
    shipping fewer pages than they picked."""
    if len(pages) <= target_pages:
        return pages, len(pages) < target_pages
    kept, dropped = pages[:target_pages], pages[target_pages:]
    dropped_photo_ids = [
        it["photo_id"]
        for pg in dropped
        for it in (pg.get("items") or [])
        if it.get("type") == "photo" and it.get("photo_id")
    ]
    if dropped_photo_ids:
        await db.photos.update_many({"id": {"$in": dropped_photo_ids}}, {"$set": {"is_selected": False}})
    return kept, False

async def run_ai_processing(album_id: str, user_id: str):
    """Background task: analyze photos, mark duplicates, generate layout from scratch.
    The album's first page (title page) is always preserved as-is — whatever
    the user already has there, edited or still the default — only the pages
    after it are (re)generated from the photos."""
    try:
        await db.albums.update_one({"id": album_id}, {"$set": {"status": "processing"}})
        album = await db.albums.find_one({"id": album_id}, {"_id": 0})
        existing_pages = (album.get("pages") or []) if album else []
        title_page = existing_pages[0] if existing_pages else make_title_page(album.get("title") if album else None)

        photos = await db.photos.find({"album_id": album_id, "is_deleted": False}, {"_id": 0}).to_list(1000)
        if not photos:
            await db.albums.update_one({"id": album_id}, {"$set": {"status": "ready", "pages": [title_page]}})
            return

        selected, curation_stats = await _curate_photos(photos)
        orientation = album.get("orientation", "portrait") if album else "portrait"
        target_pages = album.get("target_pages", 50) if album else 50
        pages = [title_page] + deterministic_layout(selected, orientation)
        pages, fell_short = await _trim_pages_to_target(pages, target_pages)

        await db.albums.update_one(
            {"id": album_id},
            {"$set": {"pages": pages, "status": "ready", "pages_below_target": fell_short, "curation_stats": curation_stats, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        logger.info(
            f"AI processing complete for album {album_id}: {curation_stats['total_in']} photos in "
            f"→ {curation_stats['duplicates_removed']} duplicates removed, "
            f"{curation_stats['low_sharpness_removed']} rejected for low sharpness, "
            f"{len(selected)} selected, {len(pages)} pages"
        )
    except Exception as e:
        logger.error(f"AI processing error: {e}")
        await db.albums.update_one({"id": album_id}, {"$set": {"status": "error"}})


async def run_ai_processing_incremental(album_id: str, user_id: str, new_photo_ids: List[str]):
    """Background task for 'Add more photos': curates only the newly added
    photos (checking them for duplicates against what's already in the album
    too) and APPENDS new pages at the end — existing pages are left exactly
    as the user edited them."""
    try:
        await db.albums.update_one({"id": album_id}, {"$set": {"status": "processing"}})
        new_photos = await db.photos.find(
            {"id": {"$in": new_photo_ids}, "is_deleted": False}, {"_id": 0}
        ).to_list(1000)
        if not new_photos:
            await db.albums.update_one({"id": album_id}, {"$set": {"status": "ready"}})
            return

        existing_selected = await db.photos.find(
            {"album_id": album_id, "is_deleted": False, "is_selected": True, "id": {"$nin": new_photo_ids}},
            {"_id": 0},
        ).to_list(2000)

        newly_selected, curation_stats = await _curate_photos(new_photos, existing_selected)

        album = await db.albums.find_one({"id": album_id}, {"_id": 0})
        orientation = album.get("orientation", "portrait") if album else "portrait"
        existing_pages = (album.get("pages") or []) if album else []
        start_idx = len(existing_pages) % len(LAYOUT_PATTERN)
        new_pages = deterministic_layout(newly_selected, orientation, pattern_start_idx=start_idx)
        combined_pages = existing_pages + new_pages
        target_pages = album.get("target_pages", 50) if album else 50
        combined_pages, fell_short = await _trim_pages_to_target(combined_pages, target_pages)

        await db.albums.update_one(
            {"id": album_id},
            {"$set": {"pages": combined_pages, "status": "ready", "pages_below_target": fell_short, "curation_stats": curation_stats, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        logger.info(f"Incremental AI processing complete for album {album_id}: +{len(newly_selected)} photos, +{len(new_pages)} pages")
    except Exception as e:
        logger.error(f"Incremental AI processing error: {e}")
        await db.albums.update_one({"id": album_id}, {"$set": {"status": "error"}})


@api_router.post("/albums/{album_id}/process")
async def start_processing(album_id: str, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")
    photo_count = await db.photos.count_documents({"album_id": album_id, "is_deleted": False})
    if photo_count == 0:
        raise HTTPException(status_code=400, detail="Ajoutez des photos avant de lancer l'IA")
    await db.albums.update_one({"id": album_id}, {"$set": {"status": "processing"}})
    # Awaited directly, not dispatched via background_tasks — Cloud Run's
    # request-based billing throttles CPU hard once a request is
    # considered "done", and a fire-and-forget background task counts as
    # done the moment this endpoint returns. For a few hundred photos of
    # real curation work (dedup comparisons, sharpness scoring), that
    # throttling was turning a job of a couple of minutes into 10+ minutes
    # that never seemed to finish. Keeping the request open for the whole
    # duration keeps it on full CPU the whole time — the frontend already
    # awaits this call before navigating, so no polling logic needs to
    # change.
    await run_ai_processing(album_id, user["id"])
    return {"status": "processing", "photo_count": photo_count}

@api_router.get("/albums/{album_id}/status")
async def get_status(album_id: str, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]}, {"_id": 0, "status": 1, "id": 1, "google_import_result": 1})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")
    return {"status": album.get("status", "draft"), "google_import_result": album.get("google_import_result")}

@api_router.post("/albums/{album_id}/add-photos")
async def add_more_photos(
    album_id: str,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    user: dict = Depends(get_current_user),
):
    """Adds new photos to an already-generated album: the AI curates only
    these new photos (still checking them for duplicates against what's
    already in the album) and appends new pages at the end — the pages the
    user already edited are left untouched."""
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")

    uploaded = await _store_many_photos(album_id, user["id"], files)
    new_ids = [p["id"] for p in uploaded]

    if not new_ids:
        raise HTTPException(status_code=400, detail="Aucune photo valide n'a pu être ajoutée")

    await db.albums.update_one({"id": album_id}, {"$set": {"status": "processing"}})
    # Awaited, not background-tasked — same throttling issue as
    # /albums/{id}/process (see its comment).
    await run_ai_processing_incremental(album_id, user["id"], new_ids)
    fresh = await db.albums.find_one({"id": album_id}, {"_id": 0, "status": 1})
    return {"status": fresh.get("status", "ready") if fresh else "ready", "added": len(new_ids)}

# ---------- PDF Export ----------
def get_page_size(size: str, orientation: str):
    sizes = {"A3": A3, "A4": A4, "A5": A5}
    base = sizes.get(size.upper(), A4)
    if orientation == "landscape":
        return landscape(base)
    return portrait(base)

def hex_to_rl_color(hex_color: str):
    try:
        return rl_colors.HexColor(hex_color)
    except Exception:
        return rl_colors.black

def decode_data_uri_image(data_uri: str):
    """Decode a `data:image/...;base64,...` string (our custom cover logos —
    heart, rings, compass — are stored this way) into an ImageReader.
    Returns None for anything else (SVG data URIs, external URLs, etc.) so
    callers can just skip drawing rather than crash."""
    try:
        if not data_uri or not data_uri.startswith("data:image/"):
            return None
        header, _, encoded = data_uri.partition(",")
        if "base64" not in header:
            return None
        if "svg" in header:
            return None  # SVG needs a separate renderer we don't have wired up
        raw = base64.b64decode(encoded)
        return ImageReader(BytesIO(raw))
    except Exception as e:
        logger.error(f"decode_data_uri_image failed: {e}")
        return None

def _render_pdf_via_browser_sync(print_url: str) -> bytes:
    """Runs entirely with Playwright's sync API. Must be called off the main
    asyncio loop (via run_in_executor) since it blocks the calling thread —
    but that's exactly why it sidesteps the Windows subprocess/event-loop
    conflict: the sync API manages its own event loop internally, in its
    own thread, independent of whatever loop uvicorn is using."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(print_url, wait_until="networkidle", timeout=30000)
        page.wait_for_selector('[data-print-ready="true"], [data-print-error="true"]', timeout=20000)
        error_el = page.query_selector('[data-print-error="true"]')
        if error_el:
            error_text = error_el.inner_text()
            raise RuntimeError(f"print page reported an error: {error_text}")
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(300)  # small buffer for images to finish painting after load
        pdf_bytes = page.pdf(print_background=True, prefer_css_page_size=True)
        browser.close()
        return pdf_bytes

@api_router.get("/albums/{album_id}/export")
async def export_pdf(album_id: str, auth: str = Query(None), authorization: str = Header(None)):
    """Generates the PDF by opening the album's dedicated print page
    (frontend/src/pages/PrintAlbum.jsx) in a headless browser and printing
    it — this is the exact same React/CSS rendering the flipbook uses, so
    the PDF is guaranteed to match it, instead of a hand-written parallel
    drawing implementation that has to be kept in sync by hand.
    Falls back to the old manual reportlab renderer if the browser export
    fails for any reason (e.g. the headless browser isn't installed), so a
    deploy issue here doesn't take down PDF export entirely."""
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    elif auth:
        token = auth
    user_id = decode_token(token) if token else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    album = await db.albums.find_one({"id": album_id, "user_id": user_id}, {"_id": 0})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")

    try:
        print_url = f"{FRONTEND_URL}/print/{album_id}?auth={token}"
        loop = asyncio.get_event_loop()
        pdf_bytes = await loop.run_in_executor(None, _render_pdf_via_browser_sync, print_url)
        filename = f"{album.get('title', 'album').replace(' ', '_')}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"Browser-based PDF export failed, falling back to reportlab: {e}")
        return await export_pdf_reportlab_legacy(album_id=album_id, auth=auth, authorization=authorization)

async def export_pdf_reportlab_legacy(album_id: str, auth: str = Query(None), authorization: str = Header(None)):
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    elif auth:
        token = auth
    user_id = decode_token(token) if token else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    album = await db.albums.find_one({"id": album_id, "user_id": user_id}, {"_id": 0})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")

    photos = await db.photos.find({"album_id": album_id, "is_deleted": False}, {"_id": 0}).to_list(2000)
    photo_map = {p["id"]: p for p in photos}

    page_size = get_page_size(album.get("size", "A4"), album.get("orientation", "portrait"))
    pw, ph = page_size
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=page_size)

    # Default cover palette (used when the user hasn't customized colors yet)
    DEFAULT_BG = "#009BB5"
    DEFAULT_ACCENT = "#F53769"
    DEFAULT_TEXT = "#63DDE0"
    cover = album.get("cover") or {}
    bg_color = cover.get("bg_color") or DEFAULT_BG
    accent_color = cover.get("accent_color") or DEFAULT_ACCENT
    text_color = cover.get("text_color") or DEFAULT_TEXT

    def draw_text_item(item, page_w, page_h, default_color="#1A1A17"):
        """Draw a text item using the same font family and proportional size
        as the web editor."""
        weight = str(item.get("font_weight", "normal")).lower()
        style = str(item.get("font_style", "normal")).lower()
        font_name = resolve_pdf_font(item.get("font"), weight)
        # Oblique/italic isn't available for the embedded weights we bundled —
        # ReportLab's base-14 Helvetica-Oblique is the only italic we can
        # honor; anything else just skips the slant rather than crash.
        if style == "italic" and font_name in ("Helvetica", "Helvetica-Bold"):
            font_name += "-Oblique" if font_name == "Helvetica" else "Oblique"
        raw_size = float(item.get("font_size", 16))
        font_size = raw_size * (page_w / REFERENCE_PAGE_PX)
        c.setFillColor(hex_to_rl_color(item.get("color", default_color)))
        c.setFont(font_name, font_size)
        x = item["x"] * page_w
        y_top = (1 - item["y"]) * page_h
        text_align = item.get("text_align", "left")
        content = (item.get("content", "") or "")
        if item.get("role") == "subtitle":
            content = content.upper()

        # Word-wrap each manual paragraph (split on "\n") to fit the box
        # width — without this, a long line with no manual break just runs
        # off both sides of the page instead of staying inside its frame.
        box_w = item.get("w", 1) * page_w
        wrapped_lines = []
        for paragraph in content.split("\n"):
            words = paragraph.split(" ")
            cur = ""
            for w in words:
                candidate = (cur + " " + w).strip()
                if not cur or pdfmetrics.stringWidth(candidate, font_name, font_size) <= box_w:
                    cur = candidate
                else:
                    wrapped_lines.append(cur)
                    cur = w
            wrapped_lines.append(cur)

        for i, line in enumerate(wrapped_lines):
            y = y_top - font_size * (i + 1)
            if text_align == "center":
                center_x = x + item.get("w", 0) * page_w / 2
                c.drawCentredString(center_x, y, line)
            elif text_align == "right":
                right_x = x + item.get("w", 0) * page_w
                c.drawRightString(right_x, y, line)
            else:
                c.drawString(x, y, line)

    # ---- FRONT COVER PAGE ----
    c.setFillColor(hex_to_rl_color(bg_color))
    c.rect(0, 0, pw, ph, fill=1, stroke=0)
    c.setFillColor(hex_to_rl_color(text_color))
    # Title position from cover.title_x / title_y (normalized top-left)
    title_x_norm = float(cover.get("title_x", 0.08))
    title_y_norm = float(cover.get("title_y", 0.08))
    title_font_weight = str(cover.get("title_font_weight", "600"))
    title_font_name = resolve_pdf_font(cover.get("title_font"), title_font_weight)
    if cover.get("title_font_size"):
        # An explicit size was chosen in the editor (raw px, calibrated
        # against the editor's on-screen page width) — scale it so it takes
        # up the same proportion of the page here as it did there.
        title_font_size = float(cover["title_font_size"]) * (pw / REFERENCE_PAGE_PX)
    else:
        title_font_size = min(pw, ph) * 0.09
    c.setFont(title_font_name, title_font_size)
    title = album.get("title", "Album")
    title_uppercase = cover.get("title_uppercase", True)
    title_rotation = float(cover.get("title_rotation", 0))
    title_writing_mode = cover.get("title_writing_mode")
    display_title = title.upper() if title_uppercase else title
    title_box_w = float(cover.get("title_w", 0.84)) * pw
    if title_writing_mode == "vertical-rl":
        # One continuous vertical line (not wrapped per word) — matches the
        # single-flow rendering used on the web for vertical titles.
        lines = [display_title]

        # The web fits vertical titles dynamically (length from box height,
        # thickness capped by box width) instead of trusting the stored
        # static size — without this, the PDF title stays small/thin no
        # matter how generous the box actually is.
        title_box_h = float(cover.get("title_h", 0.8)) * ph
        non_space_chars = max(1, len(display_title.replace(" ", "")))
        space_count = display_title.count(" ")
        # Matches the char_h/space_h ratio used when drawing below.
        fitted_by_length = (title_box_h * 0.92) / (non_space_chars * 1.05 + space_count * 0.4)
        fitted_by_thickness = title_box_w * 0.92
        title_font_size = min(fitted_by_length, fitted_by_thickness) * float(cover.get("title_scale", 1))
        c.setFont(title_font_name, title_font_size)
    else:
        words = display_title.split()

        # Fill the box width the same way the web editor does: scale the
        # font size so the widest resulting line takes up the full box
        # width, instead of just using the stored size verbatim (which was
        # calibrated for the old, smaller static title and left a gap here).
        def wrap_at(size):
            lines_ = []
            cur_ = ""
            for w in words:
                candidate = (cur_ + " " + w).strip()
                if pdfmetrics.stringWidth(candidate, title_font_name, size) <= title_box_w:
                    cur_ = candidate
                else:
                    if cur_:
                        lines_.append(cur_)
                    cur_ = w
            if cur_:
                lines_.append(cur_)
            return lines_

        probe_lines = wrap_at(title_font_size)
        widest = max(
            (pdfmetrics.stringWidth(line, title_font_name, title_font_size) for line in probe_lines),
            default=1,
        )
        if widest > 0:
            title_font_size = title_font_size * (title_box_w * 0.96 * float(cover.get("title_scale", 1)) / widest)
            c.setFont(title_font_name, title_font_size)
        lines = wrap_at(title_font_size)
    line_h = title_font_size * 1.05
    title_top = (1 - title_y_norm) * ph
    if title_writing_mode == "vertical-rl":
        # Each word becomes its own vertical column, columns proceeding
        # right-to-left across the title box — matches the CSS vertical-rl
        # writing mode used on the web so print output stays consistent.
        col_w = title_font_size * 1.15
        char_h = title_font_size * 1.05
        space_h = title_font_size * 0.4  # a space shouldn't take a full blank character row
        right_edge = title_box_w + title_x_norm * pw
        for col_i, line in enumerate(lines):
            col_x = right_edge - col_w * (col_i + 1)
            cursor_y = title_top
            for ch in line:
                step = space_h if ch == " " else char_h
                cursor_y -= step
                if ch != " ":
                    c.drawCentredString(col_x + col_w / 2, cursor_y, ch)
    elif title_rotation:
        c.saveState()
        c.translate(title_x_norm * pw, title_top)
        c.rotate(title_rotation)
        for i, line in enumerate(lines):
            c.drawString(0, -line_h * (i + 1), line)
        c.restoreState()
    else:
        for i, line in enumerate(lines):
            c.drawString(title_x_norm * pw, title_top - line_h * (i + 1), line)

    cover_image_path = album.get("cover_image_path")
    if cover_image_path:
        try:
            data, _ = get_object(cover_image_path)
            img = ImageReader(BytesIO(data))
            cx, cy = pw * 0.5, ph * 0.35
            box_w, box_h = pw * 0.8, ph * 0.45
            c.saveState()
            p = c.beginPath()
            p.rect(cx - box_w / 2, cy - box_h / 2, box_w, box_h)
            c.clipPath(p, stroke=0, fill=0)
            iw, ih = img.getSize()
            slot_ratio = box_w / box_h
            img_ratio = iw / ih
            if img_ratio > slot_ratio:
                draw_h = box_h
                draw_w = draw_h * img_ratio
            else:
                draw_w = box_w
                draw_h = draw_w / img_ratio
            c.drawImage(img, cx - draw_w / 2, cy - draw_h / 2, width=draw_w, height=draw_h, mask='auto')
            c.restoreState()
        except Exception as e:
            logger.error(f"Cover image draw failed: {e}")

    def draw_extra_items(items, default_accent):
        """Draw text / shape / image extra items (used by both front and back cover)."""
        for item in items or []:
            it_type = item.get("type")
            if it_type == "text":
                draw_text_item(item, pw, ph, default_color=text_color)
            elif it_type == "shape":
                x = item["x"] * pw
                y_top = (1 - item["y"]) * ph
                slot_w = item["w"] * pw
                slot_h = item["h"] * ph
                y_bottom = y_top - slot_h
                c.setFillColor(hex_to_rl_color(item.get("fill_color", default_accent)))
                if item.get("shape_type") == "circle":
                    c.ellipse(x, y_bottom, x + slot_w, y_bottom + slot_h, fill=1, stroke=0)
                else:
                    c.rect(x, y_bottom, slot_w, slot_h, fill=1, stroke=0)
            elif it_type == "image":
                try:
                    data = None
                    img = None
                    if item.get("storage_path"):
                        data, _ = get_object(item["storage_path"])
                    elif item.get("asset") in BUNDLED_ASSETS_BYTES:
                        data = BUNDLED_ASSETS_BYTES[item["asset"]]
                    elif item.get("image_url"):
                        # Our custom-drawn logos (rings, heart, compass...) are
                        # stored as raw base64 data URIs, not an uploaded file
                        # or a pre-bundled asset name.
                        img = decode_data_uri_image(item["image_url"])
                    if data:
                        img = ImageReader(BytesIO(data))
                    if img:
                        x = item["x"] * pw
                        y_top = (1 - item["y"]) * ph
                        slot_w = item["w"] * pw
                        slot_h = item["h"] * ph
                        # "contain" fit (preserve aspect ratio, no crop) — this is a logo/graphic, not a photo
                        iw, ih = img.getSize()
                        ratio = min(slot_w / iw, slot_h / ih) if iw and ih else 1
                        draw_w, draw_h = iw * ratio, ih * ratio
                        cx = x + slot_w / 2
                        cy_top = y_top - slot_h / 2
                        c.drawImage(img, cx - draw_w / 2, cy_top - draw_h / 2, width=draw_w, height=draw_h, mask='auto')
                except Exception as e:
                    logger.error(f"Cover extra image draw failed: {e}")

    # Extra items on front cover (text / shape / image)
    # The subtitle sits right at the title box's real bottom edge, sized
    # proportionally to the title — matches the web editor, where both are
    # computed dynamically instead of using the template's static stored
    # values (which were calibrated for the old, smaller static title).
    title_visual_h_frac = (line_h * len(lines)) / ph if lines else 0
    front_extra_items = cover.get("extra_items", []) or []
    adjusted_extra_items = []
    for item in front_extra_items:
        if item.get("type") == "text" and item.get("role") == "subtitle":
            item = {
                **item,
                "y": title_y_norm + title_visual_h_frac,
                "font_size": title_font_size * (REFERENCE_PAGE_PX / pw) * 0.58,
            }
        adjusted_extra_items.append(item)

    draw_extra_items(adjusted_extra_items, accent_color)
    c.showPage()

    # ---- SPINE (its own narrow page, since the interior/cover pages are
    # otherwise all fixed to the same page_size — a merged single wide
    # "back+spine+front" sheet would need restructuring the whole cover
    # drawing code below, which the other cover art still depends on) ----
    num_interior_pages = len(album.get("pages", []) or [])
    spine_w = max(16, min(35, 4 + num_interior_pages * 0.12)) * 2.83465  # mm -> pt, thickness scales with page count
    c.setPageSize((spine_w, ph))
    c.setFillColor(hex_to_rl_color(bg_color))
    c.rect(0, 0, spine_w, ph, fill=1, stroke=0)

    spine_text_color = cover.get("spine_title_color") or text_color
    spine_max_font = spine_w * 0.9  # never let the text get thicker than the spine itself

    def fit_spine_font(text_str, font_name, box_h_frac):
        box_h = box_h_frac * ph
        size = 40.0
        while size > 4 and pdfmetrics.stringWidth(text_str, font_name, size) > box_h * 0.9:
            size -= 0.5
        return min(size, spine_max_font)

    # Title (mirrors the web: album title, or a spine-specific override, in
    # small caps, rotated to read top-to-bottom along the spine)
    spine_title_str = (cover.get("spine_title_text") or album.get("title", "Album")).upper()
    spine_title_font = resolve_pdf_font(cover.get("spine_title_font"), cover.get("spine_title_weight", "600"))
    title_box_y = cover.get("spine_title_y", 0.08)
    title_box_h = cover.get("spine_title_h", 0.8)
    spine_title_size = fit_spine_font(spine_title_str, spine_title_font, title_box_h)
    c.setFont(spine_title_font, spine_title_size)
    c.setFillColor(hex_to_rl_color(spine_text_color))
    c.saveState()
    title_cy = ph * (1 - title_box_y - title_box_h / 2)
    c.translate(spine_w / 2, title_cy)
    c.rotate(-90)
    c.drawCentredString(0, 0, spine_title_str)
    c.restoreState()

    # Caption (e.g. "MEMORIES") — one rotated line per manual line break
    spine_caption_str = cover.get("spine_caption")
    if spine_caption_str:
        cap_font = resolve_pdf_font(cover.get("spine_caption_font"), cover.get("spine_caption_weight", "600"))
        cap_lines = str(spine_caption_str).split("\n")
        cap_box_y = cover.get("spine_caption_y", 0.64)
        cap_box_h = cover.get("spine_caption_h", 0.24)
        cap_color = cover.get("spine_caption_color") or spine_text_color
        per_line_h = cap_box_h / max(1, len(cap_lines))
        cap_size = min(fit_spine_font(max(cap_lines, key=len), cap_font, per_line_h), spine_max_font / max(1, len(cap_lines)))
        c.setFont(cap_font, cap_size)
        c.setFillColor(hex_to_rl_color(cap_color))
        for i, line in enumerate(cap_lines):
            line_cy = ph * (1 - cap_box_y - per_line_h * (i + 0.5))
            c.saveState()
            c.translate(spine_w / 2, line_cy)
            c.rotate(-90)
            c.drawCentredString(0, 0, line.upper())
            c.restoreState()

    # Logo (heart / rings / compass...) — a plain image, only its own
    # explicit rotation (if any) applies, independent of the text rotation
    spine_logo_img = decode_data_uri_image(cover.get("spine_logo_image"))
    if spine_logo_img:
        lx = cover.get("spine_logo_x", 0.1) * spine_w
        ly_top = ph * (1 - cover.get("spine_logo_y", 0.46))
        lw = cover.get("spine_logo_w", 0.8) * spine_w
        lh = cover.get("spine_logo_h", 0.16) * ph
        iw, ih = spine_logo_img.getSize()
        ratio = min(lw / iw, lh / ih) if iw and ih else 1
        draw_w, draw_h = iw * ratio, ih * ratio
        lcx, lcy = lx + lw / 2, ly_top - lh / 2
        c.saveState()
        rot = float(cover.get("spine_logo_rotation", 0) or 0)
        if rot:
            c.translate(lcx, lcy)
            c.rotate(rot)
            c.drawImage(spine_logo_img, -draw_w / 2, -draw_h / 2, width=draw_w, height=draw_h, mask="auto")
        else:
            c.drawImage(spine_logo_img, lcx - draw_w / 2, lcy - draw_h / 2, width=draw_w, height=draw_h, mask="auto")
        c.restoreState()

    c.showPage()
    c.setPageSize((pw, ph))

    # ---- CONTENT PAGES ----
    pages = album.get("pages", []) or []
    for page in pages:
        c.setFillColor(hex_to_rl_color("#F9F8F6"))
        c.rect(0, 0, pw, ph, fill=1, stroke=0)
        items = page.get("items", [])
        for item in items:
            if item.get("type") == "photo":
                photo = photo_map.get(item.get("photo_id"))
                if not photo:
                    continue
                try:
                    data, _ = get_object(photo["storage_path"])
                    img = ImageReader(BytesIO(data))
                    x = item["x"] * pw
                    # ReportLab y-origin is bottom-left; our items use top-left origin
                    y_top = (1 - item["y"]) * ph
                    slot_w = item["w"] * pw
                    slot_h = item["h"] * ph
                    y_bottom = y_top - slot_h
                    scale = max(float(item.get("scale", 1.0)), 1.0)
                    focal_x = float(item.get("focal_x", 0.5))
                    focal_y = float(item.get("focal_y", 0.5))
                    rotation = float(item.get("rotation", 0))
                    iw, ih = img.getSize()
                    slot_ratio = slot_w / slot_h if slot_h else 1
                    img_ratio = iw / ih if ih else 1
                    # cover fit
                    if img_ratio > slot_ratio:
                        draw_h = slot_h
                        draw_w = draw_h * img_ratio
                    else:
                        draw_w = slot_w
                        draw_h = draw_w / img_ratio
                    # apply zoom
                    draw_w *= scale
                    draw_h *= scale
                    # focal offset (0..1). 0.5 = centered
                    overflow_x = draw_w - slot_w
                    overflow_y = draw_h - slot_h
                    img_x = x - overflow_x * focal_x
                    img_y_top = y_top + overflow_y * focal_y
                    img_y_bottom = img_y_top - draw_h
                    # clip
                    c.saveState()
                    p = c.beginPath()
                    p.rect(x, y_bottom, slot_w, slot_h)
                    c.clipPath(p, stroke=0, fill=0)
                    if rotation:
                        # rotate the photo around the frame's own center — the
                        # frame itself (its position/size) never changes.
                        cx, cy = x + slot_w / 2, y_bottom + slot_h / 2
                        c.translate(cx, cy)
                        c.rotate(rotation)
                        c.translate(-cx, -cy)
                    c.drawImage(img, img_x, img_y_bottom, width=draw_w, height=draw_h, mask='auto')
                    c.restoreState()
                except Exception as e:
                    logger.error(f"PDF image draw failed: {e}")
            elif item.get("type") == "text":
                draw_text_item(item, pw, ph)
        c.showPage()

    # ---- BACK COVER ----
    c.setFillColor(hex_to_rl_color(bg_color))
    c.rect(0, 0, pw, ph, fill=1, stroke=0)
    c.setFillColor(hex_to_rl_color(text_color))
    back_items = cover.get("back_extra_items", []) or []
    # Legacy fallback: older albums without back_extra_items still get the
    # fixed country/year text. New albums seed real (editable) text items instead.
    if not back_items:
        c.setFont("Helvetica", min(pw, ph) * 0.04)
        country_text = album.get("country", "") or ""
        if country_text and not cover.get("hide_back_text"):
            c.drawCentredString(pw / 2, ph * 0.5, country_text.upper())
        c.setFont("Helvetica", min(pw, ph) * 0.025)
        c.drawCentredString(pw / 2, ph * 0.1, str(album.get("year", "")))
    draw_extra_items(back_items, accent_color)
    c.showPage()

    c.save()
    buf.seek(0)
    filename = f"{album.get('title', 'album').replace(' ', '_')}.pdf"
    return Response(
        content=buf.read(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

# ---------- Orders ----------
ORDER_STATUS_LABELS = {
    "pending_payment": "Payment pending",
    "paid": "Payment confirmed",
    "processing": "Preparing your album",
    "printing": "Printing",
    "shipped": "Shipped",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}
# The order in which a normal (non-cancelled) order is expected to progress —
# drives the tracking timeline on the frontend.
ORDER_STATUS_SEQUENCE = ["pending_payment", "paid", "processing", "printing", "shipped", "delivered"]

async def _generate_order_pdf(order_id: str, album_id: str, user_id: str):
    """Runs in the background right after an order is created. Reuses the
    exact same browser-based renderer as the (now customer-facing-removed)
    PDF export, so the file the team sends to the printer is guaranteed to
    match what the customer saw in the flipbook. Never surfaced to the
    customer directly — this is purely for internal/printer use."""
    try:
        token = create_token(user_id)
        print_url = f"{FRONTEND_URL}/print/{album_id}?auth={token}"
        loop = asyncio.get_event_loop()
        pdf_bytes = await loop.run_in_executor(None, _render_pdf_via_browser_sync, print_url)
        path = f"{APP_NAME}/orders/{order_id}.pdf"
        put_object(path, pdf_bytes, "application/pdf")
        await db.orders.update_one({"id": order_id}, {"$set": {"pdf_path": path, "pdf_ready": True}})
    except Exception as e:
        logger.error(f"Échec de la génération du PDF pour la commande {order_id}: {e}")
        await db.orders.update_one({"id": order_id}, {"$set": {"pdf_ready": False, "pdf_error": str(e)}})

async def _delete_unselected_photos(album_id: str):
    """Runs in the background right after an order is created. The photos
    the AI didn't select (duplicates, blurry rejects) were never going to
    appear in the printed book — once the album is actually ordered there's
    no remaining reason to keep them on R2, so we delete the files and mark
    them is_deleted so they stop showing up anywhere in the app."""
    try:
        unselected = await db.photos.find(
            {"album_id": album_id, "is_deleted": False, "is_selected": False}, {"_id": 0}
        ).to_list(5000)
        for p in unselected:
            delete_object(p.get("storage_path"))
            delete_object(p.get("thumbnail_path"))
            delete_object(p.get("medium_path"))
        ids = [p["id"] for p in unselected]
        if ids:
            await db.photos.update_many({"id": {"$in": ids}}, {"$set": {"is_deleted": True}})
    except Exception as e:
        logger.error(f"Échec du nettoyage des photos non sélectionnées pour l'album {album_id}: {e}")

@api_router.post("/orders")
async def create_order(data: OrderCreate, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": data.album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")
    if not album.get("pages"):
        raise HTTPException(status_code=400, detail="Cet album n'a pas encore de pages")
    unit_price = compute_order_price_cents(album.get("size", "A4"), album.get("target_pages", 50))
    order_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    order_doc = {
        "id": order_id,
        "user_id": user["id"],
        "album_id": album["id"],
        "album_title": album.get("title", "Album"),
        "size": album.get("size", "A4"),
        "orientation": album.get("orientation", "portrait"),
        "quantity": data.quantity,
        "unit_price_cents": unit_price,
        "total_price_cents": unit_price * data.quantity,
        "currency": "eur",
        "shipping_address": data.shipping_address.dict(),
        "status": "pending_payment",
        "status_history": [{"status": "pending_payment", "at": now}],
        "pdf_ready": False,
        "pdf_path": None,
        "tracking_number": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.orders.insert_one(order_doc)
    background_tasks.add_task(_generate_order_pdf, order_id, album["id"], user["id"])
    background_tasks.add_task(_delete_unselected_photos, album["id"])
    order_doc.pop("_id", None)
    return order_doc

@api_router.get("/orders")
async def list_orders(user: dict = Depends(get_current_user)):
    orders = await db.orders.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return orders

@api_router.get("/orders/{order_id}")
async def get_order(order_id: str, user: dict = Depends(get_current_user)):
    order = await db.orders.find_one({"id": order_id, "user_id": user["id"]}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")
    if order["status"] == "cancelled":
        timeline = [{"status": "cancelled", "label": ORDER_STATUS_LABELS["cancelled"], "done": True}]
    else:
        current_idx = ORDER_STATUS_SEQUENCE.index(order["status"]) if order["status"] in ORDER_STATUS_SEQUENCE else 0
        timeline = [
            {"status": s, "label": ORDER_STATUS_LABELS[s], "done": i <= current_idx}
            for i, s in enumerate(ORDER_STATUS_SEQUENCE)
        ]
    order["timeline"] = timeline
    order["status_label"] = ORDER_STATUS_LABELS.get(order["status"], order["status"])
    return order

# ---------- Maintenance ----------
@api_router.post("/internal/cleanup-expired-albums")
async def cleanup_expired_albums(x_cleanup_secret: str = Header(None)):
    """Deletes albums that were never ordered and are older than
    DRAFT_ALBUM_RETENTION_DAYS (default 30) — their photos on R2, cover
    image, and the album document itself. An ordered album is never touched
    here regardless of age (see _delete_unselected_photos for what happens
    to its unselected photos, at order time instead).

    Not reachable by end users — meant to be called on a schedule by Cloud
    Scheduler, authenticated with CLEANUP_SECRET rather than a user token,
    since there's no logged-in user in that context.
    """
    if not CLEANUP_SECRET:
        raise HTTPException(status_code=500, detail="CLEANUP_SECRET n'est pas configuré sur ce serveur")
    if x_cleanup_secret != CLEANUP_SECRET:
        raise HTTPException(status_code=401, detail="Non autorisé")

    cutoff = (datetime.now(timezone.utc) - timedelta(days=DRAFT_ALBUM_RETENTION_DAYS)).isoformat()
    ordered_album_ids = set(await db.orders.distinct("album_id"))

    candidates = await db.albums.find(
        {"is_deleted": {"$ne": True}, "created_at": {"$lt": cutoff}}, {"_id": 0}
    ).to_list(2000)

    deleted_count = 0
    for album in candidates:
        if album["id"] in ordered_album_ids:
            continue  # ever ordered, however long ago — never auto-purged
        photos = await db.photos.find({"album_id": album["id"]}, {"_id": 0}).to_list(5000)
        for p in photos:
            delete_object(p.get("storage_path"))
            delete_object(p.get("thumbnail_path"))
            delete_object(p.get("medium_path"))
        delete_object(album.get("cover_image_path"))
        await db.photos.update_many({"album_id": album["id"]}, {"$set": {"is_deleted": True}})
        await db.albums.update_one({"id": album["id"]}, {"$set": {"is_deleted": True}})
        deleted_count += 1

    return {"checked": len(candidates), "deleted": deleted_count, "retention_days": DRAFT_ALBUM_RETENTION_DAYS}

# ---------- Health ----------
@api_router.get("/")
async def root():
    return {"status": "ok", "service": "Album AI Studio"}

# Include router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
