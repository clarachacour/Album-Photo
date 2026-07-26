import os
import re
import io
import json
import uuid
import secrets
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from io import BytesIO

from fastapi import (
    FastAPI, 
    APIRouter, 
    Depends, 
    HTTPException, 
    Query, 
    Header, 
    BackgroundTasks, 
    UploadFile, 
    File, 
    Form, 
    status
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, EmailStr, Field

# Imports MongoDB (Motor)
import motor.motor_asyncio

# Imports Google GenAI SDK (Officiel)
from google import genai
from google.genai import types

# Imports ReportLab pour l'export PDF
from reportlab.lib.pagesizes import A4, A5, landscape, portrait
from reportlab.lib import colors as rl_colors
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# Config Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("album_ai_studio")

# Initialisation de l'application FastAPI
app = FastAPI(title="Album AI Studio API", version="1.0.0")
api_router = APIRouter(prefix="/api")

# Configuration MongoDB & Stockage
MONGO_DETAILS = os.environ.get("MONGO_DETAILS", "mongodb://localhost:27017")
STORAGE_DIR = os.environ.get("STORAGE_DIR", "./storage")
os.makedirs(STORAGE_DIR, exist_ok=True)

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_DETAILS)
db = client.album_studio_db

# Assets embarqués factices
BUNDLED_ASSETS_BYTES = {}

# ------------------------------------------------------------------------------
# MODÈLES PYDANTIC
# ------------------------------------------------------------------------------

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = "Utilisateur"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class AlbumCreate(BaseModel):
    title: str = "Mon Album"
    country: Optional[str] = ""
    year: Optional[int] = 2026
    size: str = "A4"  # A4 ou A5
    orientation: str = "portrait"  # portrait ou landscape

class AlbumUpdate(BaseModel):
    title: Optional[str] = None
    country: Optional[str] = None
    year: Optional[int] = None
    size: Optional[str] = None
    orientation: Optional[str] = None
    cover: Optional[Dict[str, Any]] = None
    pages: Optional[List[Dict[str, Any]]] = None

# ------------------------------------------------------------------------------
# SÉCURITÉ & HELPER FUNCTIONS
# ------------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash le mot de passe (SHA-256 pour l'exemple, à adapter si vous utilisez Passlib/Bcrypt)."""
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest()

def create_access_token(user_id: str) -> str:
    """Génère un token simple (utilisez PyJWT en production si nécessaire)."""
    return f"token_{user_id}_{secrets.token_hex(16)}"

def decode_token(token: str) -> Optional[str]:
    """Extrait l'ID utilisateur à partir du token."""
    if token and token.startswith("token_"):
        parts = token.split("_")
        if len(parts) >= 2:
            return parts[1]
    return None

async def get_current_user(authorization: str = Header(None)) -> dict:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Non authentifié")
    
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")
    return user

def save_object(file_bytes: bytes, filename: str) -> str:
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(filename)[1] or ".jpg"
    storage_path = os.path.join(STORAGE_DIR, f"{file_id}{ext}")
    with open(storage_path, "wb") as f:
        f.write(file_bytes)
    return storage_path

def get_object(storage_path: str):
    if os.path.exists(storage_path):
        with open(storage_path, "rb") as f:
            return f.read(), "image/jpeg"
    raise FileNotFoundError(f"Fichier non trouvé : {storage_path}")

def hamming_distance(hash1: Optional[str], hash2: Optional[str]) -> int:
    if not hash1 or not hash2 or len(hash1) != len(hash2):
        return 999
    try:
        return bin(int(hash1, 16) ^ int(hash2, 16)).count('1')
    except ValueError:
        return 999

def cluster_by_location(photos: List[dict]) -> List[List[dict]]:
    return [photos]

def deterministic_layout(photos: List[dict], orientation: str) -> List[dict]:
    pages = []
    for idx, photo in enumerate(photos):
        pages.append({
            "page_number": idx + 1,
            "items": [
                {
                    "type": "photo",
                    "photo_id": photo["id"],
                    "x": 0.1, "y": 0.1,
                    "w": 0.8, "h": 0.8,
                    "scale": 1.0,
                    "focal_x": photo.get("ai_focal_x", 0.5),
                    "focal_y": photo.get("ai_focal_y", 0.5)
                }
            ]
        })
    return pages

# ------------------------------------------------------------------------------
# ENDPOINTS AUTHENTIFICATION & COMPTE
# ------------------------------------------------------------------------------

@api_router.post("/auth/register")
async def register(payload: UserRegister):
    existing = await db.users.find_one({"email": payload.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Un compte existe déjà avec cet email.")
    
    user_id = str(uuid.uuid4())
    user_doc = {
        "id": user_id,
        "email": payload.email.lower(),
        "password": hash_password(payload.password),
        "name": payload.name,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(user_doc)
    
    token = create_access_token(user_id)
    return {"token": token, "user": {"id": user_id, "email": user_doc["email"], "name": user_doc["name"]}}

@api_router.post("/auth/login")
async def login(payload: UserLogin):
    user = await db.users.find_one({
        "email": payload.email.lower(),
        "password": hash_password(payload.password)
    })
    if not user:
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect.")
    
    token = create_access_token(user["id"])
    return {"token": token, "user": {"id": user["id"], "email": user["email"], "name": user.get("name", "")}}

@api_router.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {"id": user["id"], "email": user["email"], "name": user.get("name", "")}

@api_router.post("/auth/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest):
    """Génère un token sécurisé pour réinitialiser le mot de passe."""
    user = await db.users.find_one({"email": payload.email.lower()})
    
    if not user:
        return {"message": "Si cet email existe, un lien de réinitialisation a été envoyé."}
    
    reset_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "reset_token": reset_token,
            "reset_token_expires": expires_at
        }}
    )
    
    reset_link = f"http://localhost:3000/reset-password?token={reset_token}"
    logger.info(f"🔑 [DEMANDE RÉINITIALISATION] Lien pour {user['email']} : {reset_link}")
    
    return {"message": "Si cet email existe, un lien de réinitialisation a été envoyé."}

@api_router.post("/auth/reset-password")
async def reset_password(payload: ResetPasswordRequest):
    """Vérifie le token et applique le nouveau mot de passe."""
    now = datetime.now(timezone.utc)
    
    user = await db.users.find_one({
        "reset_token": payload.token,
        "reset_token_expires": {"$gt": now}
    })
    
    if not user:
        raise HTTPException(
            status_code=400, 
            detail="Le jeton de réinitialisation est invalide ou a expiré."
        )
    
    hashed_pwd = hash_password(payload.new_password)
    
    await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"password": hashed_pwd},
            "$unset": {"reset_token": "", "reset_token_expires": ""}
        }
    )
    
    return {"message": "Mot de passe réinitialisé avec succès ! Vous pouvez maintenant vous connecter."}

# ------------------------------------------------------------------------------
# ENDPOINTS CRUD ALBUMS & PHOTOS
# ------------------------------------------------------------------------------

@api_router.post("/albums")
async def create_album(payload: AlbumCreate, user: dict = Depends(get_current_user)):
    album_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    album_doc = {
        "id": album_id,
        "user_id": user["id"],
        "title": payload.title,
        "country": payload.country,
        "year": payload.year,
        "size": payload.size,
        "orientation": payload.orientation,
        "status": "draft",
        "cover": {
            "bg_color": "#009BB5",
            "accent_color": "#F53769",
            "text_color": "#63DDE0",
            "title_x": 0.08,
            "title_y": 0.08,
            "extra_items": [],
            "back_extra_items": []
        },
        "pages": [],
        "created_at": now,
        "updated_at": now
    }
    await db.albums.insert_one(album_doc)
    album_doc.pop("_id", None)
    return album_doc

@api_router.get("/albums")
async def list_albums(user: dict = Depends(get_current_user)):
    albums = await db.albums.find({"user_id": user["id"]}, {"_id": 0}).to_list(100)
    return albums

@api_router.get("/albums/{album_id}")
async def get_album(album_id: str, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]}, {"_id": 0})
    if not album:
        raise HTTPException(status_code=404, detail="Album non trouvé.")
    return album

@api_router.put("/albums/{album_id}")
async def update_album(album_id: str, payload: AlbumUpdate, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album non trouvé.")
    
    update_data = {k: v for k, v in payload.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.albums.update_one({"id": album_id}, {"$set": update_data})
    updated_album = await db.albums.find_one({"id": album_id}, {"_id": 0})
    return updated_album

@api_router.delete("/albums/{album_id}")
async def delete_album(album_id: str, user: dict = Depends(get_current_user)):
    res = await db.albums.delete_one({"id": album_id, "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Album non trouvé.")
    await db.photos.delete_many({"album_id": album_id})
    return {"message": "Album supprimé avec succès."}

@api_router.post("/albums/{album_id}/photos")
async def upload_photos(album_id: str, files: List[UploadFile] = File(...), user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album non trouvé.")
    
    saved_photos = []
    for file in files:
        content = await file.read()
        storage_path = save_object(content, file.filename)
        photo_id = str(uuid.uuid4())
        
        photo_doc = {
            "id": photo_id,
            "album_id": album_id,
            "user_id": user["id"],
            "filename": file.filename,
            "storage_path": storage_path,
            "content_type": file.content_type,
            "is_deleted": False,
            "is_selected": True,
            "is_duplicate": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.photos.insert_one(photo_doc)
        photo_doc.pop("_id", None)
        saved_photos.append(photo_doc)
        
    return saved_photos

@api_router.get("/albums/{album_id}/photos")
async def list_photos(album_id: str, user: dict = Depends(get_current_user)):
    photos = await db.photos.find({"album_id": album_id, "is_deleted": False}, {"_id": 0}).to_list(1000)
    return photos

# ------------------------------------------------------------------------------
# PIPELINE DE TRAITEMENT IA & ALBUMS
# ------------------------------------------------------------------------------

async def analyze_photo_batch(photos_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        logger.error("Aucune clé GEMINI_API_KEY trouvée.")
        raise ValueError("Clé API Gemini manquante.")

    client = genai.Client(api_key=api_key)

    prompt_text = """
    Vous êtes un éditeur photo professionnel pour un livre d'art.
    Analysez chaque image du lot fourni et renvoyez STRICTEMENT un tableau JSON (Array d'objets).
    
    [
      {
        "photo_id": "ID_DE_LA_PHOTO",
        "description": "Courte description poétique et précise en français",
        "quality_score": 8.5,
        "group": "Catégorie ou thème",
        "is_duplicate_or_burst": false,
        "focal_x": 0.5,
        "focal_y": 0.5
      }
    ]
    """

    contents = [prompt_text]
    processed_ids = []

    for idx, item in enumerate(photos_data):
        photo_id = item.get("id") or f"photo_{idx}"
        img_bytes = item.get("bytes")
        mime_type = item.get("mime_type", "image/jpeg")

        if not img_bytes:
            continue

        processed_ids.append(photo_id)
        contents.append(f"Photo ID: {photo_id}")
        contents.append(types.Part.from_bytes(data=img_bytes, mime_type=mime_type))

    if not processed_ids:
        return []

    try:
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
                    delay = 20.0
                    match = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+(?:\.\d+)?)", err_text)
                    if match:
                        delay = float(match.group(1)) + 1
                    logger.warning(f"Limite Gemini atteinte, réessai dans {delay:.0f}s")
                    await asyncio.sleep(delay)
                    continue
                else:
                    break
        if last_error is not None:
            raise last_error

        analysis_result = json.loads(response.text)
        return analysis_result

    except Exception as e:
        logger.error(f"Erreur lors de l'analyse Gemini : {e}")
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


async def run_ai_processing(album_id: str, user_id: str):
    try:
        await db.albums.update_one({"id": album_id}, {"$set": {"status": "processing"}})
        photos = await db.photos.find({"album_id": album_id, "is_deleted": False}, {"_id": 0}).to_list(1000)
        if not photos:
            await db.albums.update_one({"id": album_id}, {"$set": {"status": "ready", "pages": []}})
            return

        photos_with_bytes = []
        for p in photos:
            try:
                img_data, ctype = get_object(p["storage_path"])
                photos_with_bytes.append({
                    "id": p["id"],
                    "bytes": img_data,
                    "mime_type": p.get("content_type") or ctype
                })
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

        for p in photos:
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

        HASH_THRESHOLD = 6
        clusters: List[List[dict]] = []
        for p in photos:
            placed = False
            for cluster in clusters:
                if hamming_distance(p.get("phash"), cluster[0].get("phash")) <= HASH_THRESHOLD:
                    cluster.append(p)
                    placed = True
                    break
            if not placed:
                clusters.append([p])

        QUALITY_FLOOR = 3.5
        selected = []
        for cluster in clusters:
            cluster.sort(key=lambda x: -(x.get("ai_score") or 0))
            best = cluster[0]
            for d in cluster[1:]:
                await db.photos.update_one({"id": d["id"]}, {"$set": {"is_duplicate": True, "is_selected": False}})
            is_clear_miss = best.get("ai_is_reject") and (best.get("ai_score") or 0) < QUALITY_FLOOR
            if is_clear_miss:
                await db.photos.update_one({"id": best["id"]}, {"$set": {"is_duplicate": True, "is_selected": False}})
            else:
                await db.photos.update_one({"id": best["id"]}, {"$set": {"is_duplicate": False, "is_selected": True}})
                selected.append(best)

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

        album = await db.albums.find_one({"id": album_id}, {"_id": 0})
        orientation = album.get("orientation", "portrait") if album else "portrait"
        pages = deterministic_layout(selected, orientation)

        await db.albums.update_one(
            {"id": album_id},
            {"$set": {"pages": pages, "status": "ready", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        logger.info(f"AI processing complete for album {album_id}: {len(selected)} photos, {len(pages)} pages")
    except Exception as e:
        logger.error(f"AI processing error: {e}")
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

# ------------------------------------------------------------------------------
# EXPORT PDF (REPORTLAB)
# ------------------------------------------------------------------------------

def get_page_size(size: str, orientation: str):
    base = A4 if size.upper() == "A4" else A5
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
        raise HTTPException(status_code=401, detail="Non authentifié")

    album = await db.albums.find_one({"id": album_id, "user_id": user_id}, {"_id": 0})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")

    photos = await db.photos.find({"album_id": album_id, "is_deleted": False}, {"_id": 0}).to_list(2000)
    photo_map = {p["id"]: p for p in photos}

    page_size = get_page_size(album.get("size", "A4"), album.get("orientation", "portrait"))
    pw, ph = page_size
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=page_size)

    DEFAULT_BG = "#009BB5"
    DEFAULT_ACCENT = "#F53769"
    DEFAULT_TEXT = "#63DDE0"
    cover = album.get("cover") or {}
    bg_color = cover.get("bg_color") or DEFAULT_BG
    accent_color = cover.get("accent_color") or DEFAULT_ACCENT
    text_color = cover.get("text_color") or DEFAULT_TEXT

    def draw_text_item(item, page_w, page_h, default_color="#1A1A17"):
        weight = str(item.get("font_weight", "normal")).lower()
        style = str(item.get("font_style", "normal")).lower()
        is_bold = weight in ("bold", "600", "700", "800", "900") or (weight.isdigit() and int(weight) >= 600)
        is_italic = style == "italic"
        if is_bold and is_italic:
            font_name = "Helvetica-BoldOblique"
        elif is_bold:
            font_name = "Helvetica-Bold"
        elif is_italic:
            font_name = "Helvetica-Oblique"
        else:
            font_name = "Helvetica"
        font_size = float(item.get("font_size", 16))
        c.setFillColor(hex_to_rl_color(item.get("color", default_color)))
        c.setFont(font_name, font_size)
        x = item["x"] * page_w
        y_top = (1 - item["y"]) * page_h
        for i, line in enumerate((item.get("content", "") or "").split("\n")):
            c.drawString(x, y_top - font_size * (i + 1), line)

    # ---- PREMIÈRE DE COUVERTURE ----
    c.setFillColor(hex_to_rl_color(bg_color))
    c.rect(0, 0, pw, ph, fill=1, stroke=0)
    c.setFillColor(hex_to_rl_color(text_color))
    title_x_norm = float(cover.get("title_x", 0.08))
    title_y_norm = float(cover.get("title_y", 0.08))
    title_font_weight = str(cover.get("title_font_weight", "600"))
    title_is_bold = title_font_weight in ("bold", "600", "700", "800", "900") or (title_font_weight.isdigit() and int(title_font_weight) >= 600)
    title_font_name = "Helvetica-Bold" if title_is_bold else "Helvetica"
    title_font_size = float(cover.get("title_font_size") or (min(pw, ph) * 0.09))
    c.setFont(title_font_name, title_font_size)
    title = album.get("title", "Album")
    words = title.upper().split()
    lines = []
    cur = ""
    max_chars = max(1, int(pw / (title_font_size * 0.55)))
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = (cur + " " + w).strip()
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
            logger.error(f"Draw image couverture échoué: {e}")
    elif not cover.get("hide_illustration") and not any((it.get("type") == "image") for it in (cover.get("extra_items") or [])):
        c.setFillColor(hex_to_rl_color(accent_color))
        c.circle(pw * 0.5, ph * 0.42, min(pw, ph) * 0.18, fill=1, stroke=0)

    def draw_extra_items(items, default_accent):
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
                        iw, ih = img.getSize()
                        ratio = min(slot_w / iw, slot_h / ih) if iw and ih else 1
                        draw_w, draw_h = iw * ratio, ih * ratio
                        cx = x + slot_w / 2
                        cy_top = y_top - slot_h / 2
                        c.drawImage(img, cx - draw_w / 2, cy_top - draw_h / 2, width=draw_w, height=draw_h, mask='auto')
                except Exception as e:
                    logger.error(f"Draw extra image couverture échoué: {e}")

    draw_extra_items(cover.get("extra_items", []), accent_color)
    c.showPage()

    # ---- PAGES DE CONTENU ----
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
                    y_top = (1 - item["y"]) * ph
                    slot_w = item["w"] * pw
                    slot_h = item["h"] * ph
                    y_bottom = y_top - slot_h
                    scale = float(item.get("scale", 1.0))
                    focal_x = float(item.get("focal_x", 0.5))
                    focal_y = float(item.get("focal_y", 0.5))
                    iw, ih = img.getSize()
                    slot_ratio = slot_w / slot_h if slot_h else 1
                    img_ratio = iw / ih if ih else 1
                    
                    if img_ratio > slot_ratio:
                        draw_h = slot_h
                        draw_w = draw_h * img_ratio
                    else:
                        draw_w = slot_w
                        draw_h = draw_w / img_ratio
                    
                    draw_w *= scale
                    draw_h *= scale
                    
                    overflow_x = draw_w - slot_w
                    overflow_y = draw_h - slot_h
                    img_x = x - overflow_x * focal_x
                    img_y_top = y_top + overflow_y * focal_y
                    img_y_bottom = img_y_top - draw_h
                    
                    c.saveState()
                    p = c.beginPath()
                    p.rect(x, y_bottom, slot_w, slot_h)
                    c.clipPath(p, stroke=0, fill=0)
                    c.drawImage(img, img_x, img_y_bottom, width=draw_w, height=draw_h, mask='auto')
                    c.restoreState()
                except Exception as e:
                    logger.error(f"Draw photo page PDF échoué: {e}")
            elif item.get("type") == "text":
                draw_text_item(item, pw, ph)
        c.showPage()

    # ---- QUATRIÈME DE COUVERTURE ----
    c.setFillColor(hex_to_rl_color(bg_color))
    c.rect(0, 0, pw, ph, fill=1, stroke=0)
    c.setFillColor(hex_to_rl_color(text_color))
    back_items = cover.get("back_extra_items", []) or []
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

# ------------------------------------------------------------------------------
# ENDPOINTS DIVERS & MIDDLEWARES
# ------------------------------------------------------------------------------

@api_router.get("/cover-templates")
async def list_cover_templates():
    return [
        {"id": "classic", "name": "Classic", "bg": "#009BB5", "accent": "#F53769", "text": "#63DDE0"},
        {"id": "minimal", "name": "Minimal", "bg": "#1A1A1A", "accent": "#FFFFFF", "text": "#E0E0E0"},
        {"id": "warm", "name": "Warm Summer", "bg": "#E07A5F", "accent": "#F2CC8F", "text": "#3D405B"}
    ]

@api_router.get("/")
async def root():
    return {"status": "ok", "service": "Album AI Studio API"}

# Attachement des routes
app.include_router(api_router)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)