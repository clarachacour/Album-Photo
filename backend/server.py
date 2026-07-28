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
import bcrypt
import jwt
import requests
import re
import asyncio
from PIL import Image, ExifTags
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

# LLM
# LLM (Google Gemini officiel)
from google import genai
from google.genai import types
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# ---------- Config ----------
MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']
JWT_SECRET = os.environ.get('JWT_SECRET', 'dev-secret')
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')
JWT_EXP_HOURS = 24 * 30
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')
APP_NAME = os.environ.get('APP_NAME', 'albumai')

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
storage_key: Optional[str] = None

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

# --------- Storage helpers (Sauvegarde locale sur PC) ----------
from pathlib import Path

# Dossier où seront stockées les images sur ton PC
LOCAL_STORAGE_DIR = Path("uploads")
if not LOCAL_STORAGE_DIR.exists():
    LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Images packagées avec l'application (ex: logo corail par défaut sur la couverture)
# Embarquées en base64 (voir cover_assets.py) pour ne jamais dépendre d'un fichier
# présent sur le disque — évite les soucis de fichier oublié lors d'un déploiement.
from cover_assets import CORAL_LOGO_BYTES
BUNDLED_ASSETS_BYTES = {
    "coral": CORAL_LOGO_BYTES,
}

def init_storage() -> Optional[str]:
    """Ne fait rien d'externe, indique juste que le stockage local est prêt."""
    return "local_storage_active"

# Exemple de correction dans la fonction de sauvegarde locale (put_object ou équivalent)
def put_object(path, data, content_type=None):
    """Sauvegarde locale sécurisée du fichier et retourne un dictionnaire avec le chemin et la taille."""
    file_path = LOCAL_STORAGE_DIR / path
    
    # S'assure uniquement que les dossiers parents existent sans perturber la racine 'uploads'
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Écriture propre des octets de l'image
    file_path.write_bytes(data)
    
    return {
        "path": path,
        "size": len(data)
    }

def get_object(path: str) -> tuple:
    """Lit le fichier directement depuis le dossier uploads du PC."""
    try:
        file_path = LOCAL_STORAGE_DIR / path
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Image non trouvée")
            
        with open(file_path, "rb") as f:
            content = f.read()
            
        # Détermination simple du type MIME
        content_type = "image/jpeg"
        if path.lower().endswith(".png"):
            content_type = "image/png"
        elif path.lower().endswith(".webp"):
            content_type = "image/webp"
            
        return content, content_type
    except Exception as e:
        logger.error(f"Erreur de lecture locale pour {path}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur de lecture locale: {e}")

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

def send_password_reset_email(to_email: str, name: str, reset_link: str):
    subject = "Reset your password"
    body = (
        f"Hi {name or ''},\n\n"
        f"Click the link below to reset your password (valid for 1 hour):\n{reset_link}\n\n"
        f"If you didn't request this, you can safely ignore this email."
    )
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        # No email provider configured — log the link so it's usable in local/dev testing
        # without silently failing. Set SMTP_HOST/SMTP_USER/SMTP_PASSWORD to send real emails.
        logger.warning(f"[DEV] SMTP non configuré — lien de réinitialisation pour {to_email} : {reset_link}")
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
        logger.error(f"Échec de l'envoi de l'email de réinitialisation : {e}")

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

class AlbumUpdate(BaseModel):
    title: Optional[str] = None
    country: Optional[str] = None
    year: Optional[int] = None
    cover_template_id: Optional[str] = None
    size: Optional[str] = None
    orientation: Optional[str] = None
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
    return UserOut(id=user["id"], email=user["email"], name=user["name"])

# ---------- Album Routes ----------
def make_title_page(title: str) -> dict:
    """The first interior page every album starts with — right after the
    cover, always right-hand (the left page of that spread stays blank), and
    pre-filled with just the album's title. The user is free to add or
    remove anything on it afterward."""
    return {
        "id": str(uuid.uuid4()),
        "layout": "title_page",
        "items": [
            {
                "id": str(uuid.uuid4()),
                "type": "text",
                "content": title or "Untitled",
                "x": 0.1,
                "y": 0.42,
                "w": 0.8,
                "h": 0.16,
                "font": "'Baloo 2', sans-serif",
                "font_weight": "800",
                "font_size": 36,
                "color": "#1A1A17",
            }
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
    return albums

@api_router.get("/albums/{album_id}")
async def get_album(album_id: str, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]}, {"_id": 0})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")
    # Also include photos
    photos = await db.photos.find({"album_id": album_id}, {"_id": 0}).to_list(1000)
    album["photos"] = photos
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
    result = await db.albums.delete_one({"id": album_id, "user_id": user["id"]})
    await db.photos.update_many({"album_id": album_id}, {"$set": {"is_deleted": True}})
    return {"deleted": result.deleted_count}

# ---------- Photo Upload ----------
ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp"}

async def _store_new_photo(album_id: str, user_id: str, filename: str, content_type: str, data: bytes) -> Optional[dict]:
    """Shared logic to persist one photo (bytes already in hand) as a Photo
    document — used by the normal upload endpoint, the phone QR upload, and
    the Google Photos import, so all three go through the exact same
    EXIF/hash/storage pipeline."""
    if content_type not in ALLOWED_MIME:
        return None
    if len(data) == 0:
        return None
    ext = (filename or "img.jpg").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"
    photo_id = str(uuid.uuid4())
    path = f"{APP_NAME}/users/{user_id}/albums/{album_id}/{photo_id}.{ext}"
    try:
        result = put_object(path, data, content_type)
    except Exception as e:
        logger.error(f"Upload failed for {filename}: {e}")
        return None
    exif_info = extract_exif_info(data)
    img_w, img_h = None, None
    try:
        with Image.open(BytesIO(data)) as _probe:
            img_w, img_h = _probe.size
    except Exception as e:
        logger.debug(f"Impossible de lire les dimensions de l'image: {e}")
    photo_doc = {
        "id": photo_id,
        "album_id": album_id,
        "user_id": user_id,
        "storage_path": result["path"],
        "original_filename": filename,
        "content_type": content_type,
        "size": result.get("size", len(data)),
        "width": img_w,
        "height": img_h,
        "ai_score": None,
        "ai_description": None,
        "ai_group": None,
        "ai_is_reject": False,
        "ai_focal_x": 0.5,
        "ai_focal_y": 0.5,
        "taken_at": exif_info["taken_at"],
        "gps_lat": exif_info["gps_lat"],
        "gps_lng": exif_info["gps_lng"],
        "phash": _ahash_to_str(compute_ahash(data)),
        "is_selected": True,
        "is_duplicate": False,
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.photos.insert_one(photo_doc)
    photo_doc.pop("_id", None)
    return photo_doc

@api_router.post("/albums/{album_id}/photos")
async def upload_photos(
    album_id: str,
    files: List[UploadFile] = File(...),
    user: dict = Depends(get_current_user),
):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")

    uploaded = []
    for f in files:
        content_type = f.content_type or "image/jpeg"
        data = await f.read()
        photo_doc = await _store_new_photo(album_id, user["id"], f.filename, content_type, data)
        if photo_doc:
            uploaded.append(photo_doc)
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
    uploaded = []
    for f in files:
        content_type = f.content_type or "image/jpeg"
        data = await f.read()
        photo_doc = await _store_new_photo(session["album_id"], session["user_id"], f.filename, content_type, data)
        if photo_doc:
            uploaded.append(photo_doc)

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
    session_id: str

@api_router.post("/albums/{album_id}/import/google-photos")
async def import_google_photos(album_id: str, data: GooglePhotosImportInput, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")

    headers = {"Authorization": f"Bearer {data.access_token}"}
    try:
        resp = requests.get(
            "https://photospicker.googleapis.com/v1/mediaItems",
            headers=headers,
            params={"sessionId": data.session_id, "pageSize": 100},
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Échec de la lecture de la sélection Google Photos : {e}")
        raise HTTPException(status_code=502, detail="Impossible de récupérer la sélection Google Photos")

    items = resp.json().get("mediaItems", [])
    uploaded = []
    for item in items:
        media_file = item.get("mediaFile", {})
        base_url = media_file.get("baseUrl")
        filename = media_file.get("filename", "photo.jpg")
        if not base_url:
            continue
        try:
            img_resp = requests.get(f"{base_url}=d", headers=headers, timeout=20)
            if img_resp.status_code != 200:
                continue
            content_type = img_resp.headers.get("Content-Type", "image/jpeg")
            photo_doc = await _store_new_photo(album_id, user["id"], filename, content_type, img_resp.content)
            if photo_doc:
                uploaded.append(photo_doc)
        except Exception as e:
            logger.error(f"Échec du téléchargement d'une photo Google Photos ({filename}) : {e}")
            continue

    if uploaded and album.get("status") == "ready":
        await db.albums.update_one({"id": album_id}, {"$set": {"status": "processing"}})
        background_tasks.add_task(run_ai_processing_incremental, album_id, user["id"], [p["id"] for p in uploaded])

    return {"uploaded": len(uploaded)}
@api_router.get("/photos/{photo_id}/image")
async def get_photo_image(photo_id: str, auth: str = Query(None), authorization: str = Header(None)):
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
    data, ctype = get_object(photo["storage_path"])
    return Response(content=data, media_type=photo.get("content_type") or ctype)

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
    result = put_object(path, data, content_type)
    await db.albums.update_one(
        {"id": album_id},
        {"$set": {
            "cover_image_path": result["path"],
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
async def get_cover_image(album_id: str, auth: str = Query(None), authorization: str = Header(None)):
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
    data, ctype = get_object(album["cover_image_path"])
    return Response(content=data, media_type=album.get("cover_image_content_type") or ctype)

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
    result = put_object(path, data, content_type)
    return {"storage_path": result["path"]}

@api_router.get("/cover-assets/image")
async def get_cover_asset_image(path: str = Query(...), auth: str = Query(None), authorization: str = Header(None)):
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
    data, ctype = get_object(path)
    return Response(content=data, media_type=ctype)


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
        img = Image.open(BytesIO(data)).convert("L").resize((8, 8), Image.LANCZOS)
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

async def analyze_photo_batch(photos_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Analyse un lot d'images avec l'API Google Gemini officielle.
    
    Chaque élément de `photos_data` doit être un dictionnaire contenant :
      - "id": identifiant unique de la photo
      - "bytes": contenu binaire de l'image (bytes)
      - "mime_type": type de l'image (ex: 'image/jpeg', 'image/png')
    """
    # Récupération de la clé API depuis l'environnement
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        logger.error("Aucune clé GEMINI_API_KEY trouvée dans les variables d'environnement.")
        raise ValueError("Clé API Gemini manquante. Ajoutez GEMINI_API_KEY dans votre fichier .env")

    # Initialisation du client officiel Google GenAI
    client = genai.Client(api_key=api_key)

    # Consignes claires pour l'IA
    prompt_text = """
    Vous êtes un éditeur photo professionnel pour un livre d'art / album photo "Coffee Table Book".
    Analysez chaque image du lot fourni et renvoyez STRICTEMENT un tableau JSON (Array d'objets).
    
    Pour CHAQUE image, générez un objet respectant exactement cette structure :
    [
      {
        "photo_id": "ID_DE_LA_PHOTO",
        "description": "Courte description poétique et précise en français",
        "quality_score": 8.5,  # Note de 1.0 à 10.0 (basée sur netteté, lumière, cadrage)
        "group": "Catégorie ou thème (ex: 'Paysages', 'Portraits', 'Gastronomie', 'Architecture')",
        "is_duplicate_or_burst": false, # true si c'est une photo floue, ratée ou doublon d'une rafale
        "focal_x": 0.5, # Centre d'intérêt horizontal (entre 0.0 et 1.0)
        "focal_y": 0.5  # Centre d'intérêt vertical (entre 0.0 et 1.0)
      }
    ]
    """

    contents = [prompt_text]
    processed_ids = []

    # Préparation des images au format attendu par le SDK Google GenAI
    for idx, item in enumerate(photos_data):
        photo_id = item.get("id") or f"photo_{idx}"
        img_bytes = item.get("bytes")
        mime_type = item.get("mime_type", "image/jpeg")

        if not img_bytes:
            continue

        processed_ids.append(photo_id)

        # Ajout du repère d'ID et de l'image sous forme de Part
        contents.append(f"Photo ID: {photo_id}")
        contents.append(
            types.Part.from_bytes(
                data=img_bytes,
                mime_type=mime_type
            )
        )

    if not processed_ids:
        return []

    try:
        # Appel à Gemini avec nouvelles tentatives automatiques en cas de
        # limite de débit (429) — respecte le délai suggéré par Google quand
        # il est présent dans la réponse d'erreur.
        MAX_RETRIES = 3
        last_error = None
        response = None
        for attempt in range(MAX_RETRIES):
            try:
                response = client.models.generate_content(
                    model="gemini-3.1-flash-lite",
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.2,
                    )
                )
                last_error = None
                break
            except Exception as retry_err:
                last_error = retry_err
                err_text = str(retry_err)
                if "429" in err_text or "RESOURCE_EXHAUSTED" in err_text:
                    delay = 20.0  # repli par défaut si le délai suggéré n'est pas trouvé
                    match = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+(?:\.\d+)?)", err_text)
                    if match:
                        delay = float(match.group(1)) + 1  # petite marge de sécurité
                    logger.warning(f"Limite Gemini atteinte, nouvelle tentative dans {delay:.0f}s (essai {attempt + 1}/{MAX_RETRIES})")
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Erreur non liée au débit (ex: 404 modèle invalide) → inutile de réessayer
                    break
        if last_error is not None:
            raise last_error

        # Lecture du résultat JSON renvoyé par l'IA
        analysis_result = json.loads(response.text)
        return analysis_result

    except Exception as e:
        logger.error(f"Erreur lors de l'analyse Gemini : {e}")
        
        # Secours (Fallback) en cas d'erreur de l'IA pour ne pas bloquer l'utilisateur
        fallback_results = []
        for pid in processed_ids:
            fallback_results.append({
                "photo_id": pid,
                "description": "Photo importée",
                "quality_score": 7.5,
                "group": "Souvenirs",
                "is_duplicate_or_burst": False,
                "focal_x": 0.5,
                "focal_y": 0.5
            })
        return fallback_results

async def _curate_photos(new_photos: List[dict], existing_selected: Optional[List[dict]] = None) -> List[dict]:
    """Runs Gemini analysis, real duplicate detection, quality selection and
    group/date/location sorting on `new_photos`. When `existing_selected` is
    given (already-placed photos elsewhere in the album), new photos are also
    checked for duplicates against them — a new photo that matches something
    already in the album is dropped, and the pre-existing photo is left
    untouched either way. Returns the final ordered list of NEW photos to
    lay out (existing photos are never included in the return value)."""
    existing_selected = existing_selected or []
    existing_ids = {e["id"] for e in existing_selected}

    # ---- Gemini analysis (only the new photos need this) ----
    photos_with_bytes = []
    for p in new_photos:
        try:
            img_data, ctype = get_object(p["storage_path"])
            photos_with_bytes.append({"id": p["id"], "bytes": img_data, "mime_type": p.get("content_type") or ctype})
        except Exception as e:
            logger.error(f"Impossible de lire les bytes pour la photo {p['id']}: {e}")

    BATCH = 5
    all_results = {}
    for i in range(0, len(photos_with_bytes), BATCH):
        batch = photos_with_bytes[i:i + BATCH]
        results = await analyze_photo_batch(batch)
        for res in results:
            all_results[res.get("photo_id")] = res
        if i + BATCH < len(photos_with_bytes):
            await asyncio.sleep(2)

    for p in new_photos:
        ai = all_results.get(p["id"], {})
        update = {
            "ai_description": ai.get("description", ""),
            "ai_score": ai.get("quality_score", 0.7),
            "ai_group": ai.get("group", "misc"),
            "ai_is_reject": bool(ai.get("is_duplicate_or_burst", False)),
            "ai_focal_x": ai.get("focal_x", 0.5),
            "ai_focal_y": ai.get("focal_y", 0.5),
        }
        await db.photos.update_one({"id": p["id"]}, {"$set": update})
        p.update(update)

    # ---- 1. Real duplicate detection (new photos vs each other AND vs what's already in the album) ----
    HASH_THRESHOLD = 6
    clusters: List[List[dict]] = [[e] for e in existing_selected]
    for p in new_photos:
        placed = False
        for cluster in clusters:
            if hamming_distance(p.get("phash"), cluster[0].get("phash")) <= HASH_THRESHOLD:
                cluster.append(p)
                placed = True
                break
        if not placed:
            clusters.append([p])

    # ---- 2. Best-photo selection ----
    QUALITY_FLOOR = 3.5
    selected = []
    for cluster in clusters:
        new_in_cluster = [c for c in cluster if c["id"] not in existing_ids]
        if not new_in_cluster:
            continue  # cluster made only of pre-existing photos — nothing new here
        cluster.sort(key=lambda x: -(x.get("ai_score") or 0))
        best = cluster[0]
        for d in cluster[1:]:
            if d["id"] in existing_ids:
                continue  # never touch a photo that was already placed elsewhere
            await db.photos.update_one({"id": d["id"]}, {"$set": {"is_duplicate": True, "is_selected": False}})
        if best["id"] in existing_ids:
            # the best shot in this cluster is already in the album — every
            # new photo here is a duplicate of it, so none of them get added
            for d in new_in_cluster:
                await db.photos.update_one({"id": d["id"]}, {"$set": {"is_duplicate": True, "is_selected": False}})
            continue
        is_clear_miss = best.get("ai_is_reject") and (best.get("ai_score") or 0) < QUALITY_FLOOR
        if is_clear_miss:
            await db.photos.update_one({"id": best["id"]}, {"$set": {"is_duplicate": True, "is_selected": False}})
        else:
            await db.photos.update_one({"id": best["id"]}, {"$set": {"is_duplicate": False, "is_selected": True}})
            selected.append(best)

    # ---- 3. Group & sort (place / date priority, same rules as the initial pass) ----
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

    return selected


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

        selected = await _curate_photos(photos)
        orientation = album.get("orientation", "portrait") if album else "portrait"
        pages = [title_page] + deterministic_layout(selected, orientation)

        await db.albums.update_one(
            {"id": album_id},
            {"$set": {"pages": pages, "status": "ready", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        logger.info(f"AI processing complete for album {album_id}: {len(selected)} photos, {len(pages)} pages")
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

        newly_selected = await _curate_photos(new_photos, existing_selected)

        album = await db.albums.find_one({"id": album_id}, {"_id": 0})
        orientation = album.get("orientation", "portrait") if album else "portrait"
        existing_pages = (album.get("pages") or []) if album else []
        start_idx = len(existing_pages) % len(LAYOUT_PATTERN)
        new_pages = deterministic_layout(newly_selected, orientation, pattern_start_idx=start_idx)
        combined_pages = existing_pages + new_pages

        await db.albums.update_one(
            {"id": album_id},
            {"$set": {"pages": combined_pages, "status": "ready", "updated_at": datetime.now(timezone.utc).isoformat()}}
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
    background_tasks.add_task(run_ai_processing, album_id, user["id"])
    return {"status": "processing", "photo_count": photo_count}

@api_router.get("/albums/{album_id}/status")
async def get_status(album_id: str, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]}, {"_id": 0, "status": 1, "id": 1})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")
    return {"status": album.get("status", "draft")}

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

    new_ids = []
    for f in files:
        content_type = f.content_type or "image/jpeg"
        data = await f.read()
        photo_doc = await _store_new_photo(album_id, user["id"], f.filename, content_type, data)
        if photo_doc:
            new_ids.append(photo_doc["id"])

    if not new_ids:
        raise HTTPException(status_code=400, detail="Aucune photo valide n'a pu être ajoutée")

    await db.albums.update_one({"id": album_id}, {"$set": {"status": "processing"}})
    background_tasks.add_task(run_ai_processing_incremental, album_id, user["id"], new_ids)
    return {"status": "processing", "added": len(new_ids)}

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

@api_router.get("/albums/{album_id}/export")
async def export_pdf(album_id: str, auth: str = Query(None), authorization: str = Header(None)):
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
        # multi-line wrap on newlines
        for i, line in enumerate((item.get("content", "") or "").split("\n")):
            c.drawString(x, y_top - font_size * (i + 1), line)

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
    words = title.upper().split()
    lines = []
    cur = ""
    title_box_w = float(cover.get("title_w", 0.84)) * pw
    for w in words:
        candidate = (cur + " " + w).strip()
        if pdfmetrics.stringWidth(candidate, title_font_name, title_font_size) <= title_box_w:
            cur = candidate
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    line_h = title_font_size * 1.05
    title_top = (1 - title_y_norm) * ph
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
                    if item.get("storage_path"):
                        data, _ = get_object(item["storage_path"])
                    elif item.get("asset") in BUNDLED_ASSETS_BYTES:
                        data = BUNDLED_ASSETS_BYTES[item["asset"]]
                    if data:
                        img = ImageReader(BytesIO(data))
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
    draw_extra_items(cover.get("extra_items", []), accent_color)
    c.showPage()

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

# ---------- Cover Templates listing ----------
@api_router.get("/cover-templates")
async def list_cover_templates():
    return [
        {"id": "default", "name": "Classic", "bg": "#0F5A67", "accent": "#E56B55", "text": "#F9F8F6"},
    ]

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