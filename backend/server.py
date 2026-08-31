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
from fastapi.responses import Response, StreamingResponse, HTMLResponse, RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
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
import hmac
import hashlib
import bcrypt
import jwt
import requests
import re
import asyncio
import threading
from PIL import Image, ExifTags, ImageOps
try:
    import pillow_heif
    pillow_heif.register_heif_opener()  # lets Image.open() read iPhone HEIC/HEIF photos — plain Pillow can't decode them on its own
except ImportError:
    logging.getLogger(__name__).warning("pillow-heif non installé — les photos HEIC/HEIF (format par défaut iPhone) échoueront au décodage")
import numpy as np
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
import time as _time
import gc

# ReportLab for PDF export
from reportlab.lib.pagesizes import A3, A4, A5, landscape, portrait
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors as rl_colors
from reportlab.pdfbase import pdfmetrics
from playwright.sync_api import sync_playwright
from pypdf import PdfReader, PdfWriter
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
# The only account allowed to see every customer's orders (name, address,
# phone, which album, the print-ready PDF, and now status changes) — set
# this to your own account's email as a Cloud Run environment variable.
# Left unset, the admin endpoints below refuse everyone rather than
# silently exposing customer data to any logged-in user.
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL')
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

# Optional — the AI-assisted duplicate resolution in _curate_photos only
# runs when this is set. Without it, curation stays 100% classical (phash +
# sharpness), same as before. Get a key from Google AI Studio
# (aistudio.google.com/apikey) and set GEMINI_API_KEY on Cloud Run to
# enable it. Deliberately the cheapest current vision-capable model — this
# is called on a handful of ambiguous clusters per album, not per photo, so
# the extra reasoning power of a bigger model isn't worth the cost here.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
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
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
# The print shop and delivery company's own inboxes — neither is a user of
# this app (no login), so every email they act on carries a signed link
# instead (see _sign_order_action). One fixed address each, since this is
# a single-operator business with one print partner and one courier; if
# that ever changes, this would need to become per-order instead of a
# flat constant.
PRINTER_EMAIL = os.environ.get("PRINTER_EMAIL")
DELIVERY_EMAIL = os.environ.get("DELIVERY_EMAIL")

def send_email(to_email: str, subject: str, body: str, html_body: str = None):
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        # No email provider configured — log it so it's usable in local/dev
        # testing without silently failing. Set SMTP_HOST/SMTP_USER/
        # SMTP_PASSWORD to send real emails.
        logger.warning(f"[DEV] SMTP non configuré — email non envoyé à {to_email} : {subject}\n{body}")
        return
    try:
        if html_body:
            # multipart/alternative: mail clients that render HTML show
            # html_body (needed for an actual clickable button); anything
            # that can't falls back to the plain-text part instead of
            # showing broken markup.
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body, "plain"))
            msg.attach(MIMEText(html_body, "html"))
        else:
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

# ---------- Printer / delivery workflow ----------
# The printer and delivery company aren't users of this app — they act on
# a specific order purely by clicking a link in an email, with no login.
# Each link is signed (HMAC, using the same secret as user auth tokens,
# but a completely different, non-JWT format — never decodable as a user
# session) so the action it grants (downloading one order's PDF, marking
# one order ready) can't be guessed or reused for a different order.
def _sign_order_action(order_id: str, action: str) -> str:
    msg = f"{order_id}:{action}".encode()
    sig = hmac.new(JWT_SECRET.encode(), msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")

def _verify_order_action(order_id: str, action: str, token: str) -> bool:
    if not token:
        return False
    expected = _sign_order_action(order_id, action)
    return hmac.compare_digest(expected, token)

def send_printer_order_email(order: dict):
    """Sent automatically the moment an order's PDF finishes generating.
    Carries a signed download link (not the file itself — a full-
    resolution album PDF can easily be tens of MB, well past what many
    inboxes accept as an attachment) and a signed "ready for delivery"
    link the printer clicks once the physical book is done, which is what
    actually notifies the delivery company — see send_delivery_pickup_email."""
    if not PRINTER_EMAIL:
        logger.warning(f"PRINTER_EMAIL non configuré — email d'impression non envoyé pour la commande {order['id']}")
        return
    download_token = _sign_order_action(order["id"], "download")
    ready_token = _sign_order_action(order["id"], "ready")
    download_url = f"{BACKEND_URL}/api/order-actions/{order['id']}/download?token={download_token}"
    ready_url = f"{BACKEND_URL}/api/order-actions/{order['id']}/ready?token={ready_token}"
    subject = f"New book to print — {order.get('album_title', 'Album')} (#{order['id'][:8]})"
    body = (
        f"New order to print.\n\n"
        f"Album: {order.get('album_title', 'Album')}\n"
        f"Format: {order.get('size')} · {order.get('orientation')}\n"
        f"Quantity: {order.get('quantity', 1)}\n\n"
        f"Download the print-ready PDF:\n{download_url}\n\n"
        f"Once printed and ready for the courier to collect, click here:\n{ready_url}"
    )
    html_body = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="margin-bottom: 4px;">New book to print</h2>
      <p style="color:#555;">{order.get('album_title', 'Album')} · {order.get('size')} {order.get('orientation')} · Qty {order.get('quantity', 1)}</p>
      <p><a href="{download_url}" style="display:inline-block; background:#1A1A17; color:#fff; padding:12px 20px; text-decoration:none; border-radius:4px;">Download print-ready PDF</a></p>
      <p style="margin-top:24px;">Once it's printed and ready for pickup:</p>
      <p><a href="{ready_url}" style="display:inline-block; background:#E56B55; color:#fff; padding:12px 20px; text-decoration:none; border-radius:4px;">Mark ready for delivery</a></p>
    </div>
    """
    send_email(PRINTER_EMAIL, subject, body, html_body=html_body)

def send_delivery_pickup_email(order: dict):
    """Sent the moment the printer clicks their "ready for delivery" link
    — the delivery company only ever needs the shipping details, never the
    PDF or any account/order-management access."""
    if not DELIVERY_EMAIL:
        logger.warning(f"DELIVERY_EMAIL non configuré — email de livraison non envoyé pour la commande {order['id']}")
        return
    addr = order.get("shipping_address") or {}
    subject = f"Ready for pickup — {order.get('album_title', 'Album')} (#{order['id'][:8]})"
    body = (
        f"A book is ready for pickup and delivery.\n\n"
        f"Deliver to:\n"
        f"{addr.get('full_name', '')}\n"
        f"{addr.get('street', '')}"
        + (f", {addr.get('building')}" if addr.get("building") else "")
        + f"\n{addr.get('city', '')}\n"
        f"Phone: {addr.get('phone', '')}\n"
        + (f"Notes: {addr.get('additional_info')}\n" if addr.get("additional_info") else "")
        + f"\nQuantity: {order.get('quantity', 1)}"
    )
    send_email(DELIVERY_EMAIL, subject, body)

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
            return existing
        raise
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
    # Computed from ADMIN_EMAIL, never stored — lets the frontend show/hide
    # the admin nav link without hardcoding the admin's address a second
    # time in frontend code (which would just be one more place for it to
    # drift out of sync with the real check, which always lives server-side
    # in require_admin regardless of what this flag says).
    is_admin: bool = False

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
    phone: str = Field(min_length=1)
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

ORDER_STATUSES = ["pending_payment", "paid", "processing", "printing", "ready_for_delivery", "shipped", "delivered", "cancelled"]

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
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")
    token = create_token(user_id)
    return AuthResponse(token=token, user=UserOut(id=user_id, email=data.email.lower(), name=data.name, is_admin=bool(ADMIN_EMAIL) and data.email.lower() == ADMIN_EMAIL))

@api_router.post("/auth/login", response_model=AuthResponse)
async def login(data: LoginInput):
    user = await db.users.find_one({"email": data.email.lower()})
    if not user or not user.get("password_hash") or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    token = create_token(user["id"])
    return AuthResponse(token=token, user=UserOut(id=user["id"], email=user["email"], name=user["name"], is_admin=bool(ADMIN_EMAIL) and user["email"] == ADMIN_EMAIL))

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
    return AuthResponse(token=token, user=UserOut(id=user["id"], email=user["email"], name=user["name"], is_admin=bool(ADMIN_EMAIL) and user["email"] == ADMIN_EMAIL))

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
    return AuthResponse(token=token, user=UserOut(id=user["id"], email=user["email"], name=user["name"], is_admin=bool(ADMIN_EMAIL) and user["email"] == ADMIN_EMAIL))

@api_router.get("/auth/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user)):
    return UserOut(
        id=user["id"], email=user["email"], name=user["name"],
        phone=user.get("phone"), street=user.get("street"),
        building=user.get("building"), city=user.get("city"),
        additional_info=user.get("additional_info"),
        is_admin=bool(ADMIN_EMAIL) and user["email"] == ADMIN_EMAIL,
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
    # is_deleted excluded — a deleted photo serves no purpose being sent to
    # the frontend at all, and including them was eating into the list cap
    # below for no reason. That cap itself used to be 1000 — comfortably
    # enough for a normal album, but 796 original photos plus a further
    # 796 re-uploaded (to recover from a batch of them going missing, for
    # instance) adds up to more than that on its own, and the excess was
    # getting silently cut off the response rather than erroring — every
    # other large-list query in this file already uses 5000, so this one
    # matches them instead of being the one exception.
    photos = await db.photos.find({"album_id": album_id, "is_deleted": {"$ne": True}}, {"_id": 0}).to_list(5000)
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
        delete_object(p.get("print_path"))
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
            # Phone cameras very often save the raw sensor pixels in one
            # orientation (frequently landscape, regardless of how the
            # phone was actually held) plus an EXIF tag saying "rotate/
            # flip this for correct display" — every viewer normally
            # applies that tag invisibly, so a photo everyone SEES as
            # portrait can have raw pixel dimensions that are actually
            # wider than they are tall, and vice versa. Every downstream
            # use of width/height (the AI layout's photo/slot aspect-ratio
            # matching in particular) was reading those raw, pre-rotation
            # dimensions — so a portrait-looking face photo could get
            # measured as landscape, get placed in a landscape-shaped
            # slot, and have the face cropped off. exif_transpose bakes
            # the rotation into the actual pixels once, here, at the
            # single shared entry point every image (photos, cover
            # images, cover assets) already goes through — so everything
            # downstream (the stored file, thumbnails, medium/print
            # variants, and the width/height recorded below) is
            # consistently already-correctly-oriented from this point on,
            # with nothing else needing its own fix.
            _probe = ImageOps.exif_transpose(_probe)
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
                # Even when no resize is needed, the re-oriented pixels
                # must still replace store_data — otherwise the file
                # actually uploaded would keep its original EXIF-rotation-
                # pending orientation while img_w/img_h (used everywhere
                # else) claim the corrected one, a mismatch worse than
                # not fixing this at all.
                out_buf = BytesIO()
                save_kwargs = {"quality": 95} if (_probe.format or "").upper() == "JPEG" else {}
                _probe.save(out_buf, format=_probe.format or "JPEG", **save_kwargs)
                store_data = out_buf.getvalue()
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

# 3000px comfortably covers true 300 DPI print quality up to A4
# (~3508px at 300dpi) and still ~250 DPI at A3 — visually indistinguishable
# from 300dpi in a printed photo album, well beyond what the eye can
# resolve at normal viewing distance. A raw phone/camera original is very
# often 6000-8000px+ on the long side (or more), which the PDF export was
# previously using directly (variant=original) — decoding dozens of those,
# all at once, for one continuous Playwright-rendered PDF covering every
# page of the whole album, is what pushed memory usage past the Cloud Run
# instance's limit and crashed the whole export. This cuts each photo's
# decoded memory footprint substantially without any visible cost to
# actual print quality.
PRINT_MAX_DIMENSION_PX = 3000

def _generate_print_variant(photo: dict):
    """Same idea as _generate_medium_variant, but sized for genuine print
    quality (PRINT_MAX_DIMENSION_PX) rather than screen viewing — this is
    what the PDF export (PrintAlbum.jsx, variant=print) uses instead of
    the true original, to keep the whole-album render within memory."""
    try:
        data, _ = get_object(photo["storage_path"])
        with Image.open(BytesIO(data)) as img:
            img = img.convert("RGB") if img.mode not in ("RGB", "L") else img.copy()
            img.thumbnail((PRINT_MAX_DIMENSION_PX, PRINT_MAX_DIMENSION_PX), Image.LANCZOS)
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=95)  # higher quality than medium — this is what actually gets printed
            print_bytes = buf.getvalue()
        print_path = photo["storage_path"].rsplit(".", 1)[0] + "_print.jpg"
        put_object(print_path, print_bytes, "image/jpeg")
        return print_path, print_bytes
    except Exception as e:
        logger.error(f"Impossible de générer la variante 'print' pour la photo {photo.get('id')}: {e}")
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
    elif variant == "print":
        # Used only by the PDF export (PrintAlbum.jsx) — sized for genuine
        # print quality (PRINT_MAX_DIMENSION_PX) but not the raw original,
        # which was pushing the whole-album Playwright render past the
        # Cloud Run instance's memory limit. Same on-demand-then-cache
        # pattern as medium above.
        if photo.get("print_path"):
            path = photo["print_path"]
            served_content_type = "image/jpeg"
        else:
            loop = asyncio.get_event_loop()
            print_path, print_bytes = await loop.run_in_executor(None, _generate_print_variant, photo)
            if print_path:
                await db.photos.update_one({"id": photo_id}, {"$set": {"print_path": print_path}})
                data = print_bytes
                return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000, immutable"})
            # Resizing failed — fall back to the true original rather than
            # silently omitting the photo from the printed album.
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

# Loaded once at first use, not per-photo — cv2's model loading has real
# overhead, and this module-level cache means every subsequent photo just
# reuses the already-loaded network. None means "not yet attempted";
# False means "attempted and failed" (e.g. the model file is missing),
# so we don't keep retrying a load that's never going to succeed.
_face_detector = None
_face_detector_load_failed = False
# OpenCV's DNN backend (which FaceDetectorYN uses under the hood) is NOT
# safe to call concurrently from multiple threads on the same network
# object — doing so anyway (photos were being face-detected several at a
# time via asyncio.gather + run_in_executor, i.e. real OS threads, all
# sharing the one _face_detector instance above) caused a native memory
# corruption crash ("double free or corruption", SIGABRT) that took down
# the entire server process, not just the one request — a plain Python
# try/except can't catch or contain that, since it happens below the
# Python interpreter entirely. This lock serializes every detect() call
# so only one ever runs at a time; YuNet is fast enough (milliseconds per
# photo) that this isn't a meaningful bottleneck even for a large album.
_face_detector_lock = threading.Lock()

def _get_face_detector():
    global _face_detector, _face_detector_load_failed
    if _face_detector is not None or _face_detector_load_failed:
        return _face_detector
    try:
        import cv2
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "face_detection_yunet.onnx")
        # input size is set per-image in compute_face_focal_point (it must
        # match the actual decoded image dimensions), (0, 0) here is just a
        # placeholder until the first real call.
        _face_detector = cv2.FaceDetectorYN.create(model_path, "", (0, 0), score_threshold=0.7)
    except Exception as e:
        logger.warning(f"Détecteur de visages indisponible (le recadrage se rabattra sur le centre de l'image) : {e}")
        _face_detector_load_failed = True
    return _face_detector

def compute_face_focal_point(data: bytes):
    """Finds faces in a photo and returns a (focal_x, focal_y) point — in
    the same 0-1, top-left-origin coordinate space the layout already uses
    for ai_focal_x/ai_focal_y — positioned so a crop centered on it keeps
    every detected face inside frame, rather than the raw geometric center
    of the photo (which is what got people's heads cropped off when they
    weren't centered in the original shot). Runs entirely locally via
    OpenCV's YuNet model — no photo or photo data is sent anywhere outside
    this server for this. Returns None (caller falls back to center) if no
    faces are found, or if the model isn't available for any reason."""
    detector = _get_face_detector()
    if detector is None:
        return None
    try:
        import cv2
        arr = np.frombuffer(data, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        h, w = img.shape[:2]
        if h == 0 or w == 0:
            return None
        # YuNet's accuracy/speed trade-off is tuned around a few hundred
        # pixels on the long side — shrinking a large original down to that
        # before detection costs nothing in the result (faces are still
        # easily resolvable) and meaningfully cuts inference time.
        MAX_DETECT_SIDE = 640
        scale = min(1.0, MAX_DETECT_SIDE / max(h, w))
        detect_img = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale)))) if scale < 1.0 else img
        dh, dw = detect_img.shape[:2]
        with _face_detector_lock:
            detector.setInputSize((dw, dh))
            _, faces = detector.detect(detect_img)
        if faces is None or len(faces) == 0:
            return None
        # Bounding-box centroid of every detected face, weighted by each
        # face's own area — a large, close/prominent face pulls the focal
        # point more than a tiny, distant one in the background, which is
        # usually the more important one to keep fully in frame.
        total_weight = 0.0
        sum_x, sum_y = 0.0, 0.0
        for f in faces:
            fx, fy, fw, fh = f[0], f[1], f[2], f[3]
            cx, cy = fx + fw / 2, fy + fh / 2
            weight = max(1.0, fw * fh)
            sum_x += cx * weight
            sum_y += cy * weight
            total_weight += weight
        if total_weight <= 0:
            return None
        # OpenCV's detection results are numpy scalars (np.float32), not
        # plain Python floats — MongoDB's BSON encoder has no idea how to
        # store those and raises on the very first save, which was
        # crashing the whole AI processing step (and leaving the album
        # with no pages at all) any time a face was actually detected.
        focal_x = float(min(1.0, max(0.0, (sum_x / total_weight) / dw)))
        focal_y = float(min(1.0, max(0.0, (sum_y / total_weight) / dh)))
        return (focal_x, focal_y)
    except Exception as e:
        logger.debug(f"Détection de visages échouée pour une photo (on garde le centre par défaut) : {e}")
        return None

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

TEMPLATE_PHOTO_COUNT = {
    "single_full": 1, "single_centered": 1,
    "dual_vertical": 2, "dual_horizontal": 2,
    "triptych": 3,
    "quad_grid": 4, "hero_strip": 4,
}

def deterministic_layout(photos: List[dict], orientation: str, pattern_start_idx: int = 0, content_pages_budget: Optional[int] = None) -> List[dict]:
    """Distribute photos across pages with varied layouts.
    Returns a list of pages (each with items containing photo refs and positions in normalized 0-1 coordinates).

    content_pages_budget, when given, is how many content pages (not
    counting the title page) this call must land on exactly — the page
    count the person chose and is being charged for. Without it, the
    layout just cycles LAYOUT_PATTERN and produces however many pages the
    photos happen to fill at that pattern's ~2.4 photos/page average,
    which routinely undershot a much larger chosen page count with no way
    to recover afterwards. With a budget, template picks are capped page
    by page so there's always at least 1 photo left for every remaining
    page, guaranteeing the exact target whenever there are at least as
    many photos as pages to fill.
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
        that mismatch is what causes heavy, awkward cropping. Photos with a
        detected face (ai_has_face, see _curate_photos) get an extra cost
        penalty for a poorly-matching slot — the crop can be centered on the
        face (see compute_face_focal_point), but that only helps if the
        slot's own shape isn't wildly different from the photo's to begin
        with; the slot CHOICE, not just where the crop is centered within
        it, is what determines how much of the photo (and how much risk to
        the face) has to be cropped away. This can mean a face photo "loses"
        the closest-matching slot to a non-face photo that matched it even
        better — an intentional trade, since the non-face photo has nothing
        at risk from a so-so match."""
        import math
        FACE_MISMATCH_PENALTY = 2.5
        slot_aspects = [(s["w"] / s["h"]) * page_aspect_wh for s in slots]
        remaining_slots = list(range(len(slots)))
        remaining_candidates = list(range(len(candidates)))
        assignment: Dict[int, int] = {}
        while remaining_slots and remaining_candidates:
            best = None
            for si in remaining_slots:
                for ci in remaining_candidates:
                    cost = abs(math.log(slot_aspects[si] / photo_aspect(candidates[ci])))
                    if candidates[ci].get("ai_has_face"):
                        cost *= FACE_MISMATCH_PENALTY
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
        if content_pages_budget is not None:
            remaining_budget = content_pages_budget - len(pages)
            if remaining_budget <= 0:
                break  # target already reached — leftover photos stay unused rather than overshooting
            max_template_size = max(1, len(remaining) - (remaining_budget - 1))
        else:
            max_template_size = 4

        tries = 0
        while TEMPLATE_PHOTO_COUNT[pattern[p_idx % len(pattern)]] > max_template_size and tries < len(pattern):
            p_idx += 1
            tries += 1
        layout_name = pattern[p_idx % len(pattern)]
        if TEMPLATE_PHOTO_COUNT[layout_name] > max_template_size:
            layout_name = "single_full"  # always fits — guarantees forward progress even at a 1-photo-per-page budget

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

AMBIGUOUS_CLUSTER_MIN_SIZE = 2  # even a 2-photo cluster is worth a check — low-detail scenes (water, sky, sunsets) can hash close enough to merge as "duplicates" while being genuinely different photos
AMBIGUOUS_MAX_DISTANCE_FOR_CONFIDENT_MATCH = 2  # only near-pixel-identical skips the AI call now — 4 was letting genuinely-different low-detail scenes (water, sky) through as "obviously the same" unchecked

async def _resolve_ambiguous_cluster_with_ai(cluster: List[dict]) -> List[List[dict]]:
    """Asks Gemini whether the photos in a classically-merged cluster are
    really the same photographed moment, or different photos that just
    look similar to a crude pixel-hash — exactly where average-hash
    comparison struggles: a wide sky, open sea, or a sunset can produce
    near-identical hashes across genuinely different shots, since the hash
    only sees a coarse 8x8 grayscale gradient, not color or real content.

    Returns a list of sub-groups (each a list of photos to treat as one
    duplicate cluster) — the classical cluster is split according to the
    AI's grouping, so multiple representatives can survive out of what
    classical matching treated as a single duplicate group. On any
    failure (no API key, network error, malformed response), returns the
    cluster unchanged as a single group — nothing about the classical
    result depends on this succeeding."""
    if not GEMINI_API_KEY or len(cluster) < 2:
        return [cluster]
    try:
        loop = asyncio.get_event_loop()
        parts = []
        for p in cluster:
            read_path = p.get("thumbnail_path") or p["storage_path"]
            data, _ = await loop.run_in_executor(None, get_object, read_path)
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(data).decode("ascii")}})
        prompt = (
            f"These are {len(cluster)} photos, numbered 0 to {len(cluster) - 1} in the order given. "
            "A simple image-similarity check flagged them as possible duplicates of each other. "
            "Some may genuinely be near-identical shots of the exact same moment (e.g. burst-mode "
            "frames, or the same subject photographed seconds apart). Others may just be visually "
            "similar in a generic way — for example several different sunsets, or different patches "
            "of open water or sky — without being the same photographed moment. "
            "Group the photo numbers so photos in the same group are the same shot/moment, and "
            "photos in different groups are genuinely different photos. "
            "Respond with ONLY a JSON array of arrays of integers (every number 0.."
            f"{len(cluster) - 1} must appear exactly once), e.g. [[0,1],[2],[3,4]]. No other text."
        )
        parts.append({"text": prompt})
        resp = await loop.run_in_executor(
            None,
            lambda: requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
                headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                json={"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json"}},
                timeout=30,
            ),
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        groups_idx = json.loads(text)

        seen = set()
        groups: List[List[dict]] = []
        for g in groups_idx:
            sub = []
            for idx in g:
                if not isinstance(idx, int) or idx < 0 or idx >= len(cluster) or idx in seen:
                    raise ValueError(f"Indice invalide ou dupliqué dans la réponse Gemini : {idx}")
                seen.add(idx)
                sub.append(cluster[idx])
            if sub:
                groups.append(sub)
        if seen != set(range(len(cluster))):
            raise ValueError("La réponse Gemini ne couvre pas toutes les photos du groupe")
        return groups
    except Exception as e:
        logger.warning(f"Résolution IA d'un groupe ambigu échouée (on garde le regroupement classique) : {e}")
        return [cluster]

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
    # closer to each other to be treated as the same shot.
    #
    # NOTE: curation_stats from a real 796-photo batch showed this step
    # responsible for 564 of 566 total removals (nearly all of them) —
    # BURST_HASH_THRESHOLD=20 on a 64-bit hash means up to 31% of the hash
    # could differ and two photos taken within 45s still got merged as
    # "the same shot", which is loose enough to catch genuinely different
    # framings/subjects photographed close together in time, not just true
    # bursts. Tightened on both axes (hash distance and time window)
    # pending a before/after comparison from curation_stats on the next
    # real batch. ----
    HASH_THRESHOLD = 8
    BURST_HASH_THRESHOLD = 12
    BURST_SECONDS = 20
    # ~50m — "standing in the same spot", a much tighter radius than
    # cluster_by_location's 1.5km (which groups whole album SECTIONS, not
    # individual shots) — used as a second anchor for the loose burst
    # threshold when two photos have GPS but no usable timestamp gap.
    MOMENT_GPS_KM = 0.05

    def _parse_taken_at(p):
        ts = p.get("taken_at")
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return None

    def _same_spot(p, other, radius_km):
        lat1, lng1 = p.get("gps_lat"), p.get("gps_lng")
        lat2, lng2 = other.get("gps_lat"), other.get("gps_lng")
        if lat1 is None or lng1 is None or lat2 is None or lng2 is None:
            return False
        return haversine_km(lat1, lng1, lat2, lng2) <= radius_km

    def _is_match(p, other):
        dist = hamming_distance(p.get("phash"), other.get("phash"))
        t1, t2 = _parse_taken_at(p), _parse_taken_at(other)
        if t1 and t2 and abs((t1 - t2).total_seconds()) <= BURST_SECONDS:
            return dist <= BURST_HASH_THRESHOLD
        # No usable timestamp gap (one or both missing, or too far apart) —
        # GPS is the next-best anchor: photographed from the same spot is
        # almost as strong a same-subject signal as taken moments apart.
        if _same_spot(p, other, MOMENT_GPS_KM):
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

    # ---- 1b. AI-assisted resolution for ambiguous clusters — targeted,
    # not universal. Only clusters where classical matching is genuinely
    # uncertain (several photos merged, without being near-pixel-identical)
    # get a single Gemini call each, asking specifically whether they're
    # really the same shot or just visually similar in a generic way. Small
    # clusters and confidently-identical ones are skipped entirely, so a
    # 795-photo album gets a handful of AI calls, not one per photo — and
    # with no GEMINI_API_KEY set, this whole step is a no-op and curation
    # stays 100% classical, same as before. Only clusters made entirely of
    # NEW photos are eligible — a cluster anchored by an already-existing
    # photo (the incremental "add more photos" case) is left as-is, since
    # splitting it would need re-deciding which split points to the
    # existing anchor, which isn't worth the complexity for that rarer
    # path. ----
    ai_clusters_resolved = 0
    ai_photos_recovered = 0
    ai_calls_attempted = 0
    if GEMINI_API_KEY:
        expanded_clusters: List[List[dict]] = []
        for cluster in clusters:
            new_in_cluster = [c for c in cluster if c["id"] not in existing_ids]
            if cluster[0]["id"] in existing_ids or len(new_in_cluster) < AMBIGUOUS_CLUSTER_MIN_SIZE:
                expanded_clusters.append(cluster)
                continue
            max_dist = max(
                (hamming_distance(a.get("phash"), b.get("phash"))
                 for i, a in enumerate(new_in_cluster) for b in new_in_cluster[i + 1:]),
                default=0,
            )
            if max_dist <= AMBIGUOUS_MAX_DISTANCE_FOR_CONFIDENT_MATCH:
                expanded_clusters.append(cluster)
                continue
            ai_calls_attempted += 1
            sub_groups = await _resolve_ambiguous_cluster_with_ai(new_in_cluster)
            if len(sub_groups) > 1:
                ai_clusters_resolved += 1
                ai_photos_recovered += len(sub_groups) - 1
                # Step 3b (below) re-checks visual similarity with its own,
                # cruder classical threshold — without this tag it would
                # routinely re-merge exactly what the AI just spent a call
                # confirming were genuinely different photos (e.g. two
                # different sunsets), silently undoing the AI's judgment.
                # Two photos only skip step 3b's check when they were both
                # examined in *this* AI call but landed in *different*
                # sub-groups — an AI call resolving some OTHER cluster
                # doesn't affect them.
                resolution_id = ai_calls_attempted
                for group_idx, sg in enumerate(sub_groups):
                    for p in sg:
                        p["_ai_group"] = (resolution_id, group_idx)
            expanded_clusters.extend(sub_groups)
        clusters = expanded_clusters

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
    passing_reps = []
    for rep in representatives:
        score = rep_sharpness.get(rep["id"], 0.0)
        is_reject = score < SHARPNESS_FLOOR
        rep["ai_score"] = score
        if is_reject:
            await db.photos.update_one({"id": rep["id"]}, {"$set": {"ai_score": score, "ai_is_reject": True, "is_duplicate": True, "is_selected": False}})
            low_sharpness_removed += 1
        else:
            passing_reps.append(rep)

    # Face-aware focal point — finds where any people actually are in the
    # photo (fully locally, via the OpenCV/YuNet model — nothing about the
    # photo is sent anywhere for this) so the layout can center its crop on
    # them instead of the raw geometric middle of the frame, which is what
    # was cropping people out when they weren't centered in the original
    # shot. Only computed for photos that passed the sharpness gate above —
    # no point spending the time on ones that won't be used anyway. Falls
    # back to dead center (the previous, only, behavior) for any photo with
    # no detected face — a landscape or an object shot, say.
    async def _focal_point_of(p):
        try:
            read_path = p.get("thumbnail_path") or p["storage_path"]
            data, _ = await loop.run_in_executor(None, get_object, read_path)
            return await loop.run_in_executor(None, compute_face_focal_point, data)
        except Exception:
            return None

    focal_points = await asyncio.gather(*(_focal_point_of(p) for p in passing_reps))
    faces_detected_count = sum(1 for f in focal_points if f)

    for rep, focal in zip(passing_reps, focal_points):
        focal_x, focal_y = focal if focal else (0.5, 0.5)
        update = {
            "ai_score": rep["ai_score"],
            "ai_is_reject": False,
            "ai_focal_x": focal_x,
            "ai_focal_y": focal_y,
            # Separate explicit flag rather than inferring "has a face" from
            # the coordinates themselves — a genuinely centered face would
            # also land on (0.5, 0.5) and be indistinguishable from "no
            # face found" if we didn't. The layout step (deterministic_layout,
            # see best_slot_assignment) uses this to prefer a well-matching
            # slot for a photo with a face over a badly-mismatched one, since
            # the slot choice itself — not just where within it the crop is
            # centered — is what determines how much has to be cropped away.
            "ai_has_face": bool(focal),
        }
        await db.photos.update_one({"id": rep["id"]}, {"$set": {**update, "is_duplicate": False, "is_selected": True}})
        rep.update(update)
        selected.append(rep)

    # ---- 3b. Visual diversity cap — catches near-identical FRAMING of the
    # same subject that step 1's stricter duplicate check correctly leaves
    # as distinct photos (different enough pixel-for-pixel to not be flagged
    # as the "same shot"), but that still reads as repetitive to a person —
    # e.g. several photos of the same wide view taken a few minutes apart
    # while wandering around one spot. Only the sharpest photo per "moment"
    # survives (MAX_PER_MOMENT=1) — the rest are dropped outright, not
    # spread elsewhere in the album, so the final album doesn't carry
    # several near-identical frames of the same subject. This also frees up
    # page space for photos from OTHER moments that would otherwise have
    # been squeezed out once the page budget ran low.
    #
    # Matching cascades through whatever signal two photos actually share —
    # date, then GPS, then visual similarity alone — instead of requiring a
    # date on both sides (the original version of this step did, which
    # meant it silently did nothing at all for photos without EXIF dates,
    # exactly the photos this cap most needed to cover). ----
    MOMENT_HASH_THRESHOLD = 16
    MOMENT_SECONDS = 300
    MOMENT_HASH_THRESHOLD_NO_ANCHOR = 10  # tighter than MOMENT_HASH_THRESHOLD — no date or GPS to corroborate, so demand a closer visual match before treating two photos as the same moment
    MAX_PER_MOMENT = 1
    redundant_removed = 0

    def _moment_match(p, other):
        # The AI already looked at these two together and explicitly said
        # "different photos" — don't let this cruder classical check
        # silently re-merge them regardless of how visually similar they
        # look.
        p_group, o_group = p.get("_ai_group"), other.get("_ai_group")
        if p_group and o_group and p_group[0] == o_group[0] and p_group[1] != o_group[1]:
            return False
        dist = hamming_distance(p.get("phash"), other.get("phash"))
        if dist > MOMENT_HASH_THRESHOLD:
            return False
        t1, t2 = _parse_taken_at(p), _parse_taken_at(other)
        if t1 and t2:
            return abs((t1 - t2).total_seconds()) <= MOMENT_SECONDS
        if _same_spot(p, other, MOMENT_GPS_KM):
            return True
        # Neither a shared date nor GPS to anchor on — fall back to visual
        # similarity alone, at a tighter threshold since there's nothing
        # else corroborating that these are really the same moment.
        return dist <= MOMENT_HASH_THRESHOLD_NO_ANCHOR

    if selected:
        moment_clusters: List[List[dict]] = []
        for p in selected:
            placed = False
            for mc in moment_clusters:
                if any(_moment_match(p, m) for m in mc):
                    mc.append(p)
                    placed = True
                    break
            if not placed:
                moment_clusters.append([p])

        thinned = []
        for mc in moment_clusters:
            if len(mc) <= MAX_PER_MOMENT:
                thinned.extend(mc)
                continue
            mc_sorted = sorted(mc, key=lambda x: -(x.get("ai_score") or 0))
            keep, drop = mc_sorted[:MAX_PER_MOMENT], mc_sorted[MAX_PER_MOMENT:]
            for d in drop:
                await db.photos.update_one({"id": d["id"]}, {"$set": {"is_duplicate": True, "is_selected": False}})
            redundant_removed += len(drop)
            thinned.extend(keep)
        selected = thinned

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
        "redundant_removed": redundant_removed,
        "ai_clusters_resolved": ai_clusters_resolved,
        "ai_calls_attempted": ai_calls_attempted,
        "ai_photos_recovered": ai_photos_recovered,
        "faces_detected": faces_detected_count,
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

        photos = await db.photos.find({"album_id": album_id, "is_deleted": False}, {"_id": 0}).to_list(5000)
        if not photos:
            await db.albums.update_one({"id": album_id}, {"$set": {"status": "ready", "pages": [title_page]}})
            return

        selected, curation_stats = await _curate_photos(photos)
        orientation = album.get("orientation", "portrait") if album else "portrait"
        target_pages = album.get("target_pages", 50) if album else 50
        pages = [title_page] + deterministic_layout(selected, orientation, content_pages_budget=max(0, target_pages - 1))
        pages, fell_short = await _trim_pages_to_target(pages, target_pages)

        await db.albums.update_one(
            {"id": album_id},
            {"$set": {"pages": pages, "status": "ready", "pages_below_target": fell_short, "curation_stats": curation_stats, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        logger.info(
            f"AI processing complete for album {album_id}: {curation_stats['total_in']} photos in "
            f"→ {curation_stats['duplicates_removed']} duplicates removed, "
            f"{curation_stats['low_sharpness_removed']} rejected for low sharpness, "
            f"{curation_stats['redundant_removed']} thinned as visually redundant, "
            f"{curation_stats['ai_calls_attempted']} ambiguous clusters sent to AI, "
            f"{curation_stats['ai_clusters_resolved']} split by AI "
            f"({curation_stats['ai_photos_recovered']} extra photos recovered), "
            f"{curation_stats['faces_detected']} photos with a detected face (crop centered on it), "
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
        new_pages = deterministic_layout(newly_selected, orientation, pattern_start_idx=start_idx, content_pages_budget=max(0, (album.get("target_pages", 50) if album else 50) - 1 - max(0, len(existing_pages) - 1)))
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


class RepackPagesInput(BaseModel):
    target_pages: int = Field(gt=0)
    keep_first_pages: int = Field(ge=0, default=0)  # e.g. 40 — pages the person already hand-edited and doesn't want touched

@api_router.post("/albums/{album_id}/repack-pages")
async def repack_pages(album_id: str, data: RepackPagesInput, user: dict = Depends(get_current_user)):
    """Changes an already-created album's total page count (e.g. 150 → 100)
    without re-running curation — every photo already placed on the pages
    being repacked gets a denser (or sparser) layout instead, using the
    same exact-page-count algorithm as initial creation (deterministic_layout
    + content_pages_budget). The first `keep_first_pages` pages (title page,
    plus however many the person already hand-edited) are left completely
    untouched — only pages after that are rebuilt.

    Every page holds at most 4 photos (the densest template,
    TEMPLATE_PHOTO_COUNT), so shrinking the page count too aggressively
    relative to how many photos are actually in play can make it
    mathematically impossible to place all of them — this refuses outright
    rather than silently dropping photos in that case, same principle as
    the minimum-photos-required check at album creation."""
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")
    pages = album.get("pages") or []
    if not pages:
        raise HTTPException(status_code=400, detail="Cet album n'a pas encore de pages")

    keep_first_pages = max(0, min(data.keep_first_pages, len(pages)))
    preserved_pages = pages[:keep_first_pages]
    pages_to_repack = pages[keep_first_pages:]

    photo_ids_in_order = [
        it["photo_id"]
        for pg in pages_to_repack
        for it in (pg.get("items") or [])
        if it.get("type") == "photo" and it.get("photo_id")
    ]

    remaining_budget = max(0, data.target_pages - keep_first_pages)

    if not photo_ids_in_order:
        # Nothing left to repack — every remaining photo is on a preserved
        # page. If the person is asking for MORE pages than exist (the
        # common case now that the editor defaults to protecting the whole
        # album), _trim_pages_to_target alone wouldn't actually add
        # anything — it only ever shrinks, and silently leaves the album
        # short of the count just requested. Append genuinely blank,
        # single-photo-slot pages (same shape the editor's own "+" button
        # creates) to make up the difference; only actually trim when
        # target_pages calls for fewer than what's already here.
        if data.target_pages > len(pages):
            M = 0.05
            usable = 1.0 - (2 * M)
            blank_pages = [
                {
                    "id": str(uuid.uuid4()),
                    "layout": "single_full",
                    "items": [
                        {
                            "id": str(uuid.uuid4()),
                            "type": "photo",
                            "photo_id": None,
                            "focal_x": 0.5,
                            "focal_y": 0.5,
                            "scale": 1,
                            "rotation": 0,
                            "x": M, "y": M, "w": usable, "h": usable,
                        }
                    ],
                }
                for _ in range(data.target_pages - len(pages))
            ]
            final_pages = pages + blank_pages
        else:
            final_pages, _ = await _trim_pages_to_target(pages, data.target_pages)
        await db.albums.update_one(
            {"id": album_id},
            {"$set": {"pages": final_pages, "target_pages": data.target_pages, "pages_below_target": len(final_pages) < data.target_pages, "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"pages": len(final_pages), "photos_repacked": 0}

    MAX_PER_PAGE = max(TEMPLATE_PHOTO_COUNT.values())
    if remaining_budget > 0 and len(photo_ids_in_order) > remaining_budget * MAX_PER_PAGE:
        max_fittable = remaining_budget * MAX_PER_PAGE
        raise HTTPException(
            status_code=400,
            detail=(
                f"{len(photo_ids_in_order)} photos are on the pages you're asking to repack, but "
                f"{remaining_budget} pages can hold at most {max_fittable} photos ({MAX_PER_PAGE} per page). "
                f"Choose a higher page count, or keep more of the existing pages as-is."
            ),
        )

    photos_by_id = {}
    cursor = db.photos.find({"id": {"$in": photo_ids_in_order}}, {"_id": 0})
    async for p in cursor:
        photos_by_id[p["id"]] = p
    ordered_photos = [photos_by_id[pid] for pid in photo_ids_in_order if pid in photos_by_id]

    orientation = album.get("orientation", "portrait")
    start_idx = keep_first_pages % len(LAYOUT_PATTERN)
    new_pages = deterministic_layout(ordered_photos, orientation, pattern_start_idx=start_idx, content_pages_budget=remaining_budget)

    final_pages = preserved_pages + new_pages
    await db.albums.update_one(
        {"id": album_id},
        {"$set": {"pages": final_pages, "target_pages": data.target_pages, "pages_below_target": len(final_pages) < data.target_pages, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"pages": len(final_pages), "photos_repacked": len(ordered_photos)}


@api_router.post("/albums/{album_id}/process")
async def start_processing(album_id: str, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")
    photo_count = await db.photos.count_documents({"album_id": album_id, "is_deleted": False})
    if photo_count == 0:
        raise HTTPException(status_code=400, detail="Ajoutez des photos avant de lancer l'IA")
    # Same hard floor the frontend already blocks on before letting the
    # person click through — enforced here too since this endpoint is
    # reachable directly. The layout always uses at least 1 photo per
    # page, so filling target_pages is mathematically impossible below
    # this count no matter how good the photos are.
    target_pages = album.get("target_pages", 50)
    minimum_required = max(0, target_pages - 1)
    if photo_count < minimum_required:
        raise HTTPException(
            status_code=400,
            detail=f"At least {minimum_required} photos are required for a {target_pages}-page album ({photo_count} uploaded)",
        )
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

def _render_pdf_with_page(page, print_url: str) -> bytes:
    """The actual per-URL render, taking an already-open Playwright Page —
    factored out of _render_pdf_via_browser_sync so a whole order's worth
    of chunks can share one launched browser (see that function's
    docstring for why relaunching Chromium per chunk was itself a real
    chunk of the total generation time on a large album)."""
    page.goto(print_url, wait_until="networkidle", timeout=30000)
    page.wait_for_selector('[data-print-ready="true"], [data-print-error="true"]', timeout=20000)
    error_el = page.query_selector('[data-print-error="true"]')
    if error_el:
        error_text = error_el.inner_text()
        raise RuntimeError(f"print page reported an error: {error_text}")
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(500)  # extra buffer for final paint settling, on top of the 1.2s the print page itself now waits before signaling ready (see PrintAlbum.jsx)
    return page.pdf(print_background=True, prefer_css_page_size=True)

def _render_pdf_via_browser_sync(print_url: str) -> bytes:
    """Runs entirely with Playwright's sync API. Must be called off the main
    asyncio loop (via run_in_executor) since it blocks the calling thread —
    but that's exactly why it sidesteps the Windows subprocess/event-loop
    conflict: the sync API manages its own event loop internally, in its
    own thread, independent of whatever loop uvicorn is using.

    Single-shot version — launches its own browser for one render. For a
    whole order's worth of chunked renders, see _render_all_chunks below,
    which reuses one browser across every chunk instead of paying
    Chromium's ~1-2s launch cost per chunk (which alone added tens of
    seconds on a large, many-chunk album)."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        pdf_bytes = _render_pdf_with_page(page, print_url)
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
    "ready_for_delivery": "Ready for delivery",
    "shipped": "Shipped",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}
# The order in which a normal (non-cancelled) order is expected to progress —
# drives the tracking timeline on the frontend.
ORDER_STATUS_SEQUENCE = ["pending_payment", "paid", "processing", "printing", "ready_for_delivery", "shipped", "delivered"]

async def _generate_order_pdf(order_id: str, album_id: str, user_id: str):
    """Runs in the background right after an order is created. Reuses the
    exact same browser-based renderer as the (now customer-facing-removed)
    PDF export, so the file the team sends to the printer is guaranteed to
    match what the customer saw in the flipbook. Never surfaced to the
    customer directly — this is purely for internal/printer use."""
    t_start = _time.monotonic()
    try:
        # Pre-warm every used photo's "print" variant BEFORE launching the
        # browser, one at a time. Without this, the headless browser (once
        # it navigates to the print page) requests every photo's print
        # variant at once — the first time any of them is needed, each of
        # those ~dozens of concurrent requests triggers its own resize+R2
        # upload, all competing for this same small instance's limited
        # thread pool alongside the PDF task itself waiting on the whole
        # page to finish loading. That self-inflicted contention was
        # stalling the export badly enough to run into the request
        # timeout with no clean error ever logged. Sequential and boring
        # on purpose — by the time Playwright opens the page, every image
        # it needs is already a fast, uncontended cache hit.
        album_doc = await db.albums.find_one({"id": album_id}, {"pages": 1})
        interior_pages = (album_doc or {}).get("pages", [])
        photo_ids = {
            it["photo_id"]
            for pg in interior_pages
            for it in (pg.get("items") or [])
            if it.get("type") == "photo" and it.get("photo_id")
        }
        if photo_ids:
            loop = asyncio.get_event_loop()
            photos_cursor = db.photos.find({"id": {"$in": list(photo_ids)}}, {"_id": 0})
            async for photo in photos_cursor:
                if photo.get("print_path") and photo.get("print_size"):
                    continue  # already cached from an earlier order/preview, size already on record
                print_path, print_bytes = await loop.run_in_executor(None, _generate_print_variant, photo)
                if print_path:
                    await db.photos.update_one({"id": photo["id"]}, {"$set": {"print_path": print_path, "print_size": len(print_bytes)}})

        token = create_token(user_id)
        loop = asyncio.get_event_loop()

        # A large album's print-quality PDF can be big enough (many
        # hundreds of full-resolution photos) that transferring it out of
        # the headless browser hits a hard ~512MB string-length ceiling
        # the JS engine itself enforces on any single value —
        # "Page.pdf: Cannot create a string longer than 0x1fffffe8
        # characters" — a wall no amount of server memory gets past,
        # because it isn't a memory limit at all.
        #
        # Predicting the right chunk size from the source photos' own file
        # weight isn't reliable on its own — nothing confirms how large
        # Chromium's actual PDF encoding of a given set of images comes
        # out to. So this uses both: the print-variant byte weight already
        # on each photo's own record picks a *starting* chunk size close
        # to right, and a recursive split-and-retry remains as the safety
        # net for whatever the estimate still gets wrong.
        #
        # With every page capped at 4 photos (a real product constraint,
        # not an assumption) and this app's own observed print-variant
        # weights (0.5-3.6MB/photo, ~1.5MB average), a 200MB target chunk
        # holds roughly 20-30 pages on average — a meaningful drop from
        # the 80MB first tried here, which forced a 300-page album into
        # ~20+ separate chunks. Now that chunks are merged incrementally
        # as they finish (see below) rather than all held in memory until
        # the end, memory pressure is no longer the reason to keep chunks
        # small — chunk *count* is now the main cost (each one is a fresh
        # network round-trip through the print page), so the target
        # should be as large as the render ceiling comfortably allows.
        FALLBACK_PHOTO_BYTES_ESTIMATE = 2 * 1024 * 1024
        photo_sizes = {}
        if photo_ids:
            size_cursor = db.photos.find({"id": {"$in": list(photo_ids)}}, {"_id": 0, "id": 1, "print_size": 1, "size": 1})
            async for p in size_cursor:
                photo_sizes[p["id"]] = p.get("print_size") or p.get("size") or FALLBACK_PHOTO_BYTES_ESTIMATE

        TARGET_INITIAL_CHUNK_BYTES = 200 * 1024 * 1024

        def _page_bytes(pg):
            return sum(
                photo_sizes.get(it.get("photo_id"), 0)
                for it in (pg.get("items") or [])
                if it.get("type") == "photo" and it.get("photo_id")
            )

        # Initial chunk boundaries from the byte estimate — computed here
        # (needs the async DB-backed photo_sizes above) but handed whole
        # to _render_all_chunks below, which does the actual rendering
        # entirely synchronously so every chunk (and every recursive
        # split-retry) can share the one browser it launches once, instead
        # of each chunk paying its own ~1-2s Chromium launch cost — on a
        # 20+-chunk album that overhead alone was tens of seconds.
        initial_ranges = []
        interior_count = len(interior_pages)
        if interior_count:
            chunk_start = 0
            chunk_bytes_so_far = 0
            for i, pg in enumerate(interior_pages):
                pg_bytes = _page_bytes(pg)
                if chunk_bytes_so_far > 0 and chunk_bytes_so_far + pg_bytes > TARGET_INITIAL_CHUNK_BYTES:
                    initial_ranges.append((chunk_start, i - 1))
                    chunk_start = i
                    chunk_bytes_so_far = 0
                chunk_bytes_so_far += pg_bytes
            initial_ranges.append((chunk_start, interior_count - 1))

        def _render_all_chunks(ranges: List[tuple]) -> bytes:
            """Everything from here down runs in one executor thread, on
            one launched browser, reusing a single Page across every
            chunk (and every recursive split-retry) via .goto() to a new
            URL each time rather than a fresh browser.new_page() or
            browser relaunch — Chromium's own launch overhead is real and
            was adding up across a large album's many chunks."""
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()

                def render_recursive(start: int, end: int, depth: int = 0) -> bytes:
                    chunk_url = f"{FRONTEND_URL}/print/{album_id}?auth={token}&from={start}&to={end}"
                    t0 = _time.monotonic()
                    try:
                        chunk_bytes = _render_pdf_with_page(page, chunk_url)
                        elapsed = _time.monotonic() - t0
                        logger.info(f"Commande {order_id} : pages {start}-{end} (profondeur {depth}) → {len(chunk_bytes)/1024/1024:.0f} Mio en {elapsed:.1f}s")
                        return chunk_bytes
                    except Exception as e:
                        elapsed = _time.monotonic() - t0
                        if start == end:
                            logger.error(f"Commande {order_id} : la page {start} seule dépasse la limite après {elapsed:.1f}s, impossible de la découper davantage : {e}")
                            raise
                        mid = (start + end) // 2
                        logger.info(f"Commande {order_id} : pages {start}-{end} ont échoué après {elapsed:.1f}s ({e}) — nouveau découpage en {start}-{mid} et {mid+1}-{end}")
                        first_half = render_recursive(start, mid, depth + 1)
                        second_half = render_recursive(mid + 1, end, depth + 1)
                        writer2 = PdfWriter()
                        for half in (first_half, second_half):
                            r = PdfReader(BytesIO(half))
                            for pg2 in r.pages:
                                writer2.add_page(pg2)
                        out2 = BytesIO()
                        writer2.write(out2)
                        return out2.getvalue()

                if not ranges:
                    result = _render_pdf_with_page(page, f"{FRONTEND_URL}/print/{album_id}?auth={token}")
                    browser.close()
                    return result

                writer = PdfWriter()
                for start, end in ranges:
                    chunk_bytes = render_recursive(start, end, 0)
                    reader = PdfReader(BytesIO(chunk_bytes))
                    for pg2 in reader.pages:
                        writer.add_page(pg2)
                    del chunk_bytes, reader
                    gc.collect()
                browser.close()
                out = BytesIO()
                writer.write(out)
                return out.getvalue()

        if len(initial_ranges) > 1:
            logger.info(f"Commande {order_id} : point de départ estimé — {len(initial_ranges)} morceaux ({initial_ranges})")
        pdf_bytes = await loop.run_in_executor(None, _render_all_chunks, initial_ranges)

        path = f"{APP_NAME}/orders/{order_id}.pdf"
        put_object(path, pdf_bytes, "application/pdf")
        await db.orders.update_one({"id": order_id}, {"$set": {"pdf_path": path, "pdf_ready": True}})
        logger.info(f"Commande {order_id} : PDF complet généré en {_time.monotonic() - t_start:.1f}s au total")

        # Moved in from create_order/admin_regenerate_order_pdf: this
        # function now runs as a genuine background task (see both
        # callers), so nothing is left waiting around afterward to do
        # this — it has to happen here, right after the PDF is confirmed
        # ready, or it would never happen at all.
        order = await db.orders.find_one({"id": order_id}, {"_id": 0})
        if order and order["status"] not in ("printing", "ready_for_delivery", "shipped", "delivered"):
            now2 = datetime.now(timezone.utc).isoformat()
            await db.orders.update_one(
                {"id": order_id},
                {"$set": {"status": "printing", "updated_at": now2}, "$push": {"status_history": {"status": "printing", "at": now2}}},
            )
            order["status"] = "printing"
            customer = await db.users.find_one({"id": user_id}, {"_id": 0})
            if customer:
                send_order_confirmation_email(customer.get("email"), customer.get("name"), order)
            send_printer_order_email(order)
            # Only a genuinely successful, first-time order — a real PDF a
            # printer will actually receive — has "the book is done,
            # unused photos can go" become true. Excluded from the status
            # check above on purpose: an admin regenerate on an
            # already-printing order shouldn't re-trigger this cleanup a
            # second time.
            await _delete_unselected_photos(album_id)
    except Exception as e:
        logger.error(f"Échec de la génération du PDF pour la commande {order_id}: {e}")
        await db.orders.update_one({"id": order_id}, {"$set": {"pdf_ready": False, "pdf_error": str(e)}})

async def _delete_unselected_photos(album_id: str):
    """Runs right after an order actually succeeds (never on a failed
    attempt — see create_order, this used to fire unconditionally even
    when PDF generation failed, deleting photos from an order that never
    actually went anywhere). Deletes whichever of the album's photos
    aren't placed on any page — freeing R2 space for what the printed
    book genuinely never needed.

    Checks the album's *current* pages for which photo_ids are actually
    placed, rather than trusting each photo's stored is_selected flag —
    that flag is set once, when the AI first curates the album, and goes
    stale the moment someone manually drags a previously-rejected photo
    into a page afterward (or removes a previously-selected one). Only
    ever deletes a photo confirmed absent from every current page,
    regardless of what is_selected happens to say."""
    try:
        album = await db.albums.find_one({"id": album_id}, {"pages": 1})
        used_photo_ids = {
            it.get("photo_id")
            for pg in (album or {}).get("pages", [])
            for it in (pg.get("items") or [])
            if it.get("type") == "photo" and it.get("photo_id")
        }
        all_photos = await db.photos.find({"album_id": album_id, "is_deleted": False}, {"_id": 0}).to_list(5000)
        unused = [p for p in all_photos if p["id"] not in used_photo_ids]
        for p in unused:
            delete_object(p.get("storage_path"))
            delete_object(p.get("thumbnail_path"))
            delete_object(p.get("medium_path"))
            delete_object(p.get("print_path"))
        ids = [p["id"] for p in unused]
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
    # Awaited directly, not dispatched via background_tasks. That was
    # tried first (a customer no longer waiting on a slow response
    # seemed clearly better) but turned out to be unreliable specifically
    # on Cloud Run: the platform only considers an instance "busy" while
    # an HTTP request is actively in flight — once this endpoint responds,
    # a background_tasks job can get silently killed mid-render if Cloud
    # Run decides to recycle the now-seemingly-idle instance, with no
    # error logged at all (a real album stalled past 15 minutes with
    # nothing wrong in the logs — this is almost certainly why). Keeping
    # the request open for the whole render guarantees Cloud Run keeps the
    # instance alive throughout, at the cost of a slower response — a
    # trade worth making, since a request that's slow but reliably
    # finishes beats a fast one that might silently never finish at all.
    # Depends on the request timeout being raised well past its 900s
    # default (Cloud Run allows up to 3600s) for a large album to have
    # room to actually complete.
    await _generate_order_pdf(order_id, album["id"], user["id"])
    fresh_order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return fresh_order or order_doc

@api_router.get("/order-actions/{order_id}/download")
async def order_action_download_pdf(order_id: str, token: str = Query(None)):
    """The printer's download link — no login, just the signed token
    mailed to them alongside it (see send_printer_order_email). A
    presigned R2 URL rather than proxying the bytes here, same reasoning
    as admin_download_order_pdf: a print-quality album PDF can easily
    exceed Cloud Run's own response-size ceiling on this backend, well
    separate from the render-time chunking concern."""
    if not _verify_order_action(order_id, "download", token):
        raise HTTPException(status_code=403, detail="Lien invalide ou expiré")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order or not order.get("pdf_path"):
        raise HTTPException(status_code=404, detail="PDF introuvable pour cette commande")
    url = get_r2_client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": R2_BUCKET_NAME,
            "Key": order["pdf_path"],
            "ResponseContentDisposition": f'attachment; filename="{order_id}.pdf"',
            "ResponseContentType": "application/pdf",
        },
        ExpiresIn=3600,
    )
    return RedirectResponse(url)

@api_router.get("/order-actions/{order_id}/ready")
async def order_action_mark_ready(order_id: str, token: str = Query(None)):
    """The printer's "ready for delivery" link — moves the order to
    ready_for_delivery and, right then, notifies the delivery company
    (see send_delivery_pickup_email). Returns a plain confirmation page
    since a person at the print shop is the one clicking this in their
    browser, not calling it as an API."""
    if not _verify_order_action(order_id, "ready", token):
        raise HTTPException(status_code=403, detail="Lien invalide ou expiré")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")
    if order["status"] != "ready_for_delivery":
        now = datetime.now(timezone.utc).isoformat()
        await db.orders.update_one(
            {"id": order_id},
            {"$set": {"status": "ready_for_delivery", "updated_at": now}, "$push": {"status_history": {"status": "ready_for_delivery", "at": now}}},
        )
        order["status"] = "ready_for_delivery"
        send_delivery_pickup_email(order)
    return HTMLResponse("<html><body style='font-family:sans-serif; text-align:center; padding:60px;'>"
                         "<h2>Thanks — the delivery company has been notified.</h2></body></html>")

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

def require_admin(user: dict):
    """Every admin endpoint below hand-checks this rather than something
    reusable via Depends() — deliberately simple for a single-admin
    business rather than building out a whole role system for one person's
    account."""
    if not ADMIN_EMAIL or user.get("email") != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Non autorisé")

@api_router.get("/admin/albums/{album_id}/broken-photos")
async def admin_list_broken_photos(album_id: str, user: dict = Depends(get_current_user)):
    """For one specific album, finds every page slot whose photo is
    actually missing — the exact "which photos need re-uploading, and
    where do they go" list for recovering from photos that went missing
    (see _delete_unselected_photos) or otherwise disappeared.

    Checks the real file on R2 with a lightweight HEAD request for every
    photo still on record as not deleted, rather than trusting is_deleted
    alone — that flag is only ever set by our own code's own delete paths,
    so a file that went missing some other way (deleted directly in the
    R2 dashboard, a delete that updated R2 but failed to update Mongo
    before crashing, anything outside this app's own bookkeeping) would
    have looked perfectly fine to the DB-only version of this check while
    still 404ing in the actual album. original_filename and taken_at
    (whichever the photo record still has) are included specifically to
    help recognize which physical file on your own device to re-upload."""
    require_admin(user)
    album = await db.albums.find_one({"id": album_id}, {"_id": 0})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")
    all_photo_ids = {
        it.get("photo_id")
        for pg in (album.get("pages") or [])
        for it in (pg.get("items") or [])
        if it.get("type") == "photo" and it.get("photo_id")
    }
    photos_by_id = {}
    if all_photo_ids:
        found = await db.photos.find({"id": {"$in": list(all_photo_ids)}}, {"_id": 0}).to_list(5000)
        photos_by_id = {p["id"]: p for p in found}

    def _exists_on_r2(path: str) -> bool:
        if not path:
            return False
        try:
            get_r2_client().head_object(Bucket=R2_BUCKET_NAME, Key=path)
            return True
        except Exception:
            return False

    loop = asyncio.get_event_loop()
    # HEAD requests only (no download) — still one round-trip per distinct
    # photo, so this checks each not-already-known-deleted photo exactly
    # once even if it's used on multiple pages, rather than re-checking it
    # per page slot.
    r2_exists_cache = {}
    for pid, photo in photos_by_id.items():
        if photo.get("is_deleted"):
            continue  # already known gone — no need to ask R2 too
        r2_exists_cache[pid] = await loop.run_in_executor(None, _exists_on_r2, photo.get("storage_path"))

    broken = []
    for page_idx, pg in enumerate(album.get("pages") or []):
        page_items = pg.get("items") or []
        for item_idx, item in enumerate(page_items):
            if item.get("type") != "photo":
                continue
            pid = item.get("photo_id")
            if not pid:
                # A genuinely empty slot — no photo_id at all, so there's
                # no filename/size trail left to match a re-upload against
                # automatically (see admin_repair_missing_photos, which
                # can only fill in slots that still point at *something*).
                # The nearest dated neighbors on the same page are the
                # best hint left for figuring out, by eye, roughly when
                # this photo was taken — helpful context for finding it in
                # "All your photos" to drag in by hand.
                neighbor_dates = [
                    photos_by_id.get(other.get("photo_id"), {}).get("taken_at")
                    for j, other in enumerate(page_items)
                    if j != item_idx and other.get("type") == "photo" and other.get("photo_id")
                ]
                neighbor_dates = [d for d in neighbor_dates if d]
                broken.append({
                    "page_index": page_idx,
                    "photo_id": None,
                    "reason": "empty_slot",
                    "original_filename": None,
                    "taken_at": None,
                    "nearby_dates_on_same_page": neighbor_dates,
                })
                continue
            photo = photos_by_id.get(pid)
            if photo is None:
                broken.append({"page_index": page_idx, "photo_id": pid, "reason": "no_record", "original_filename": None, "taken_at": None})
            elif photo.get("is_deleted") or not r2_exists_cache.get(pid, True):
                broken.append({
                    "page_index": page_idx,
                    "photo_id": pid,
                    "reason": "deleted" if photo.get("is_deleted") else "file_missing_on_r2",
                    "original_filename": photo.get("original_filename"),
                    "taken_at": photo.get("taken_at"),
                })
    return {"album_title": album.get("title"), "total_pages": len(album.get("pages") or []), "broken": broken}

@api_router.post("/admin/albums/{album_id}/repair-missing-photos")
async def admin_repair_missing_photos(album_id: str, user: dict = Depends(get_current_user)):
    """One-off repair tool, not a general feature — matches freshly
    re-uploaded photos (via the normal /albums/{id}/photos upload) back
    into the exact page slots that were pointing at a now-deleted photo.
    Matches on original_filename first; Google Photos re-downloads of the
    same photos don't reliably keep the same filename between two separate
    export sessions (a known Google Photos quirk — batch numbering and
    duplicate suffixes can differ), so this falls back to matching on
    exact file size (in bytes) when the filename doesn't match anything,
    since re-downloading the same photo at original quality produces an
    identical file. Only ever considers photos already uploaded into this
    same album that aren't placed on any page yet — a fresh re-upload, not
    something already in active use elsewhere in the book. Matches once
    each: two broken slots can't both claim the same re-uploaded file.
    Whatever it still can't match comes back in still_missing, same shape
    as /broken-photos, to retry after uploading what's left."""
    require_admin(user)
    album = await db.albums.find_one({"id": album_id})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")
    pages = album.get("pages") or []
    used_photo_ids = {
        it.get("photo_id")
        for pg in pages
        for it in (pg.get("items") or [])
        if it.get("type") == "photo" and it.get("photo_id")
    }
    # Two different queries on purpose: broken_photo_records needs the
    # DELETED photos too (that's the whole point — reading what a missing
    # photo's original filename/size *was*), while candidates below must
    # stay restricted to is_deleted: False (never resurrect a deleted
    # photo's own file, only match it to a fresh re-upload).
    broken_photo_records = {}
    if used_photo_ids:
        found_any = await db.photos.find({"id": {"$in": list(used_photo_ids)}}, {"_id": 0}).to_list(5000)
        broken_photo_records = {p["id"]: p for p in found_any}

    def _exists_on_r2(path: str) -> bool:
        if not path:
            return False
        try:
            get_r2_client().head_object(Bucket=R2_BUCKET_NAME, Key=path)
            return True
        except Exception:
            return False

    # Same real-R2-check as /broken-photos — is_deleted alone missed
    # photos whose file was gone on R2 without that flag ever getting set,
    # which meant this repair tool skipped them entirely (they never
    # looked "broken" enough to attempt a match for).
    loop = asyncio.get_event_loop()
    r2_exists_cache = {}
    for pid, photo in broken_photo_records.items():
        if photo.get("is_deleted"):
            continue
        r2_exists_cache[pid] = await loop.run_in_executor(None, _exists_on_r2, photo.get("storage_path"))

    candidates = await db.photos.find({"album_id": album_id, "is_deleted": False}, {"_id": 0}).to_list(5000)
    unplaced_by_filename = {}
    unplaced_by_size = {}
    for p in candidates:
        if p["id"] in used_photo_ids:
            continue  # already sitting in some page slot — not a fresh re-upload waiting to be placed
        unplaced_by_filename.setdefault(p.get("original_filename"), []).append(p)
        unplaced_by_size.setdefault(p.get("size"), []).append(p)

    fixed = []
    still_missing = []
    changed = False
    for page_idx, pg in enumerate(pages):
        for item in pg.get("items") or []:
            if item.get("type") != "photo" or not item.get("photo_id"):
                continue
            pid = item["photo_id"]
            photo = broken_photo_records.get(pid)
            is_broken = photo is None or photo.get("is_deleted") or not r2_exists_cache.get(pid, True)
            if not is_broken:
                continue
            filename = photo.get("original_filename") if photo else None
            size = photo.get("size") if photo else None
            match_method = None
            replacement = None
            by_name = unplaced_by_filename.get(filename) or []
            if filename and by_name:
                replacement = by_name.pop(0)
                match_method = "filename"
            else:
                by_size = unplaced_by_size.get(size) or []
                if size and by_size:
                    replacement = by_size.pop(0)
                    match_method = "size"
            if replacement:
                # Keep both lookup tables in sync so the same re-uploaded
                # file is never handed out twice, regardless of which one
                # a later slot happens to match through.
                other_list = unplaced_by_size if match_method == "filename" else unplaced_by_filename
                other_key = replacement.get("size") if match_method == "filename" else replacement.get("original_filename")
                if replacement in (other_list.get(other_key) or []):
                    other_list[other_key].remove(replacement)
                item["photo_id"] = replacement["id"]
                used_photo_ids.add(replacement["id"])
                changed = True
                fixed.append({"page_index": page_idx, "original_filename": filename, "new_photo_id": replacement["id"], "matched_by": match_method})
            else:
                still_missing.append({"page_index": page_idx, "original_filename": filename})

    if changed:
        await db.albums.update_one({"id": album_id}, {"$set": {"pages": pages, "updated_at": datetime.now(timezone.utc).isoformat()}})

    return {"fixed": fixed, "still_missing": still_missing}

@api_router.get("/admin/orders")
async def admin_list_orders(user: dict = Depends(get_current_user)):
    """Every order across every customer, newest first — the shipping
    name/address/phone and which album (title, id) are what you need to
    know who a given order.pdf in R2 (orders/{order_id}.pdf) actually
    belongs to and where it ships. Not scoped to user_id the way the
    customer-facing /orders is — that's exactly the point of this one."""
    require_admin(user)
    orders = await db.orders.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return orders

@api_router.get("/admin/orders/{order_id}/pdf")
async def admin_download_order_pdf(order_id: str, auth: str = Query(None), authorization: str = Header(None)):
    """Redirects straight to a short-lived, signed R2 URL rather than
    proxying the file's bytes through this backend and back out again —
    a print-quality album PDF easily runs past 100MB (24 pages, up to 4
    photos each, was 110MB), and Cloud Run enforces its own hard cap on
    how large a single HTTP response through the normal request/response
    path can be, well under that ("Response size was too large") — a
    completely different ceiling from the render-time V8 string-length
    one chunking exists for.

    Accepts the auth token via query param (same pattern as
    get_photo_image) in addition to the header, and the frontend now
    navigates the browser straight to this URL rather than fetching it
    through axios — a plain top-level navigation follows the redirect to
    R2 with no CORS involved at all, where an XHR/fetch-based request
    (axios's responseType: "blob", tried first) does still apply CORS to
    the redirect's target, and the R2 bucket has no CORS policy allowing
    this frontend's origin — the fetch was being silently blocked by the
    browser, which is why downloads kept failing with a "not ready yet"
    message despite the redirect itself working (that message is really
    just this endpoint's generic error fallback, not a sign the PDF
    itself was ever actually missing)."""
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    elif auth:
        token = auth
    user_id = decode_token(token) if token else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    require_admin(user)
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")
    if not order.get("pdf_path"):
        raise HTTPException(status_code=404, detail="Le PDF de cette commande n'est pas encore prêt")
    url = get_r2_client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": R2_BUCKET_NAME,
            "Key": order["pdf_path"],
            "ResponseContentDisposition": f'attachment; filename="{order_id}.pdf"',
            "ResponseContentType": "application/pdf",
        },
        ExpiresIn=3600,
    )
    return RedirectResponse(url)

@api_router.post("/admin/orders/{order_id}/regenerate-pdf")
async def admin_regenerate_order_pdf(order_id: str, user: dict = Depends(get_current_user)):
    """Re-runs the exact same PDF generation _generate_order_pdf already
    does for a brand-new order — for the day generation fails (memory
    limit, a stuck browser render, anything transient) and needs a retry.
    Awaited directly rather than dispatched as a background task — see
    create_order's comment on why: Cloud Run only guarantees an instance
    stays alive while a request is actively in flight, and a
    background_tasks job can get silently killed mid-render once this
    endpoint has already responded, with no error logged at all. A slower
    response that reliably finishes beats a fast one that might not."""
    require_admin(user)
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")
    await db.orders.update_one({"id": order_id}, {"$set": {"pdf_ready": False, "pdf_path": None, "pdf_error": None}})
    await _generate_order_pdf(order_id, order["album_id"], order["user_id"])
    fresh = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return fresh

class OrderStatusUpdate(BaseModel):
    status: str
    tracking_number: Optional[str] = None

# Which customer email (if any) fires automatically when an order moves
# INTO a given status — keeps "every status change tells the customer
# what's going on" as one small table instead of scattered if/elif
# branches that are easy to miss updating when a new status is added.
STATUS_CUSTOMER_EMAIL = {
    "shipped": send_order_shipped_email,
    "delivered": send_order_delivered_feedback_email,
}

@api_router.patch("/admin/orders/{order_id}/status")
async def admin_update_order_status(order_id: str, data: OrderStatusUpdate, user: dict = Depends(get_current_user)):
    """Manual status moves the printer/delivery workflow doesn't cover on
    its own — mainly marking an order "shipped" (with a tracking number)
    once the delivery company has actually handed it off, and "delivered"
    afterward. Whichever status this lands on, if it's one customers care
    about hearing (see STATUS_CUSTOMER_EMAIL), that email goes out right
    here — the same "every update tells the customer" guarantee the
    printer/delivery links already give the rest of the flow."""
    require_admin(user)
    if data.status not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail=f"Statut inconnu : {data.status}")
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")
    now = datetime.now(timezone.utc).isoformat()
    update = {"status": data.status, "updated_at": now}
    if data.tracking_number is not None:
        update["tracking_number"] = data.tracking_number
    await db.orders.update_one(
        {"id": order_id},
        {"$set": update, "$push": {"status_history": {"status": data.status, "at": now}}},
    )
    fresh = await db.orders.find_one({"id": order_id}, {"_id": 0})
    email_fn = STATUS_CUSTOMER_EMAIL.get(data.status)
    if email_fn:
        customer = await db.users.find_one({"id": order["user_id"]}, {"_id": 0})
        if customer:
            email_fn(customer.get("email"), customer.get("name"), fresh)
    return fresh

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
            delete_object(p.get("print_path"))
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
