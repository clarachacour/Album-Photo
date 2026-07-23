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
import asyncio

# ReportLab for PDF export
from reportlab.lib.pagesizes import A4, A5, landscape, portrait
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors as rl_colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# LLM
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

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
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# ---------- App ----------
app = FastAPI(title="Album AI Studio API")
api_router = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------- Storage helpers ----------
def init_storage() -> Optional[str]:
    global storage_key
    if storage_key:
        return storage_key
    if not EMERGENT_LLM_KEY:
        logger.error("EMERGENT_LLM_KEY not set")
        return None
    try:
        resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_LLM_KEY}, timeout=30)
        resp.raise_for_status()
        storage_key = resp.json()["storage_key"]
        logger.info("Storage initialized")
        return storage_key
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
        return None

def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    if not key:
        raise HTTPException(status_code=500, detail="Storage not available")
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120
    )
    if resp.status_code == 403:
        # Re-init and retry once
        global storage_key
        storage_key = None
        key = init_storage()
        resp = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=data, timeout=120
        )
    resp.raise_for_status()
    return resp.json()

def get_object(path: str) -> tuple:
    key = init_storage()
    if not key:
        raise HTTPException(status_code=500, detail="Storage not available")
    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key}, timeout=60
    )
    if resp.status_code == 403:
        global storage_key
        storage_key = None
        key = init_storage()
        resp = requests.get(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key}, timeout=60
        )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

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

class AlbumCreate(BaseModel):
    title: str
    country: str = ""
    year: int = Field(default_factory=lambda: datetime.now().year)
    cover_template_id: str = "teal-coral"
    size: str = "A4"  # A4 or A5
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
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    token = create_token(user["id"])
    return AuthResponse(token=token, user=UserOut(id=user["id"], email=user["email"], name=user["name"]))

@api_router.get("/auth/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user)):
    return UserOut(id=user["id"], email=user["email"], name=user["name"])

# ---------- Album Routes ----------
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
        "pages": [],
        "cover_image_path": None,
        "cover": {},
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
        if content_type not in ALLOWED_MIME:
            continue
        data = await f.read()
        if len(data) == 0:
            continue
        ext = (f.filename or "img.jpg").rsplit(".", 1)[-1].lower()
        if ext not in ("jpg", "jpeg", "png", "webp"):
            ext = "jpg"
        photo_id = str(uuid.uuid4())
        path = f"{APP_NAME}/users/{user['id']}/albums/{album_id}/{photo_id}.{ext}"
        try:
            result = put_object(path, data, content_type)
        except Exception as e:
            logger.error(f"Upload failed for {f.filename}: {e}")
            continue
        photo_doc = {
            "id": photo_id,
            "album_id": album_id,
            "user_id": user["id"],
            "storage_path": result["path"],
            "original_filename": f.filename,
            "content_type": content_type,
            "size": result.get("size", len(data)),
            "ai_score": None,
            "ai_description": None,
            "ai_group": None,
            "is_selected": True,
            "is_duplicate": False,
            "is_deleted": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.photos.insert_one(photo_doc)
        photo_doc.pop("_id", None)
        uploaded.append(photo_doc)
    return {"uploaded": len(uploaded), "photos": uploaded}

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


# ---------- AI Processing ----------
def deterministic_layout(photos: List[dict], orientation: str) -> List[dict]:
    """Distribute photos across pages with varied layouts.
    Returns a list of pages (each with items containing photo refs and positions in normalized 0-1 coordinates).
    """
    # Layout templates (photos per page + item boxes in normalized coords)
    # x, y, w, h in 0-1 (page space with small margin)
    M = 0.05
    layouts = {
        "single_full": [
            {"x": M, "y": M, "w": 1 - 2*M, "h": 1 - 2*M}
        ],
        "single_centered": [
            {"x": 0.15, "y": 0.15, "w": 0.7, "h": 0.7}
        ],
        "dual_horizontal": [
            {"x": M, "y": M, "w": 1 - 2*M, "h": 0.48 - M},
            {"x": M, "y": 0.52, "w": 1 - 2*M, "h": 0.48 - M},
        ],
        "dual_vertical": [
            {"x": M, "y": M, "w": 0.48 - M, "h": 1 - 2*M},
            {"x": 0.52, "y": M, "w": 0.48 - M, "h": 1 - 2*M},
        ],
        "triptych": [
            {"x": M, "y": M, "w": 0.6, "h": 1 - 2*M},
            {"x": 0.68, "y": M, "w": 0.27, "h": 0.48 - M},
            {"x": 0.68, "y": 0.52, "w": 0.27, "h": 0.48 - M},
        ],
        "quad_grid": [
            {"x": M, "y": M, "w": 0.44, "h": 0.44},
            {"x": 0.52, "y": M, "w": 0.43, "h": 0.44},
            {"x": M, "y": 0.52, "w": 0.44, "h": 0.43},
            {"x": 0.52, "y": 0.52, "w": 0.43, "h": 0.43},
        ],
        "hero_strip": [
            {"x": M, "y": M, "w": 1 - 2*M, "h": 0.62},
            {"x": M, "y": 0.68, "w": 0.29, "h": 0.27},
            {"x": 0.355, "y": 0.68, "w": 0.29, "h": 0.27},
            {"x": 0.71, "y": 0.68, "w": 0.24, "h": 0.27},
        ],
    }

    # Alternate layouts to create diversity
    pattern = ["single_full", "dual_vertical", "hero_strip", "single_centered", "quad_grid", "triptych", "dual_horizontal"]
    pages = []
    i = 0
    p_idx = 0
    while i < len(photos):
        layout_name = pattern[p_idx % len(pattern)]
        slots = layouts[layout_name]
        # Take up to len(slots) photos
        available = photos[i:i + len(slots)]
        if not available:
            break
        items = []
        for j, slot in enumerate(slots):
            if j >= len(available):
                break
            items.append({
                "id": str(uuid.uuid4()),
                "type": "photo",
                "photo_id": available[j]["id"],
                "x": slot["x"],
                "y": slot["y"],
                "w": slot["w"],
                "h": slot["h"],
            })
        pages.append({
            "id": str(uuid.uuid4()),
            "layout": layout_name,
            "items": items,
        })
        i += len(items)
        p_idx += 1
    return pages


async def analyze_photo_batch(photos: List[dict]) -> Dict[str, dict]:
    """Analyze a batch of photos using Gemini 3 Flash to get description and quality score.
    Returns {photo_id: {description, quality_score, group}}.
    Uses at most 6 photos per call for speed.
    """
    if not EMERGENT_LLM_KEY or not photos:
        return {p["id"]: {"description": "", "quality_score": 0.7, "group": "misc"} for p in photos}
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"album-ai-{uuid.uuid4()}",
            system_message=(
                "You are a photo curator for a coffee-table photo book. For each image, return a JSON object with: "
                "description (short caption 3-6 words), quality_score (float 0-1, higher = better composition/exposure), "
                "group (short semantic tag like 'landscape', 'portrait', 'food', 'architecture', 'wildlife', 'sunset'). "
                "Respond ONLY with a JSON array in the same order as the images, no prose."
            ),
        ).with_model("gemini", "gemini-3-flash-preview")

        # Build image contents
        image_contents = []
        for p in photos:
            try:
                data, _ = get_object(p["storage_path"])
                import base64
                b64 = base64.b64encode(data).decode('utf-8')
                image_contents.append(ImageContent(image_base64=b64))
            except Exception as e:
                logger.error(f"Fetching image for AI failed: {e}")
                image_contents.append(None)

        # Filter Nones
        valid_photos = [(p, ic) for p, ic in zip(photos, image_contents) if ic is not None]
        if not valid_photos:
            return {p["id"]: {"description": "", "quality_score": 0.7, "group": "misc"} for p in photos}

        msg = UserMessage(
            text=f"Analyze these {len(valid_photos)} photos and return the JSON array.",
            file_contents=[ic for _, ic in valid_photos],
        )
        response_text = await chat.send_message(msg)
        # Parse JSON
        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        parsed = json.loads(text)
        results = {}
        for (p, _), item in zip(valid_photos, parsed):
            results[p["id"]] = {
                "description": item.get("description", ""),
                "quality_score": float(item.get("quality_score", 0.7)),
                "group": item.get("group", "misc"),
            }
        # Fill missing
        for p in photos:
            if p["id"] not in results:
                results[p["id"]] = {"description": "", "quality_score": 0.7, "group": "misc"}
        return results
    except Exception as e:
        logger.error(f"AI batch analyze failed: {e}")
        return {p["id"]: {"description": "", "quality_score": 0.7, "group": "misc"} for p in photos}


async def run_ai_processing(album_id: str, user_id: str):
    """Background task: analyze photos, mark duplicates, generate layout."""
    try:
        await db.albums.update_one({"id": album_id}, {"$set": {"status": "processing"}})
        photos = await db.photos.find({"album_id": album_id, "is_deleted": False}, {"_id": 0}).to_list(1000)
        if not photos:
            await db.albums.update_one({"id": album_id}, {"$set": {"status": "ready", "pages": []}})
            return

        # Analyze in batches of 5
        BATCH = 5
        all_results = {}
        for i in range(0, len(photos), BATCH):
            batch = photos[i:i + BATCH]
            results = await analyze_photo_batch(batch)
            all_results.update(results)

        # Update photos with AI data
        for p in photos:
            ai = all_results.get(p["id"], {})
            await db.photos.update_one(
                {"id": p["id"]},
                {"$set": {
                    "ai_description": ai.get("description", ""),
                    "ai_score": ai.get("quality_score", 0.7),
                    "ai_group": ai.get("group", "misc"),
                }}
            )
            p["ai_description"] = ai.get("description", "")
            p["ai_score"] = ai.get("quality_score", 0.7)
            p["ai_group"] = ai.get("group", "misc")

        # Deduplication: within same group, keep the higher-scoring; mark others as duplicate if 3+ in group
        by_group: Dict[str, List[dict]] = {}
        for p in photos:
            g = p.get("ai_group", "misc")
            by_group.setdefault(g, []).append(p)

        selected = []
        for g, items in by_group.items():
            items.sort(key=lambda x: -(x.get("ai_score") or 0))
            # Keep top 60% per group, min 1
            keep_count = max(1, int(len(items) * 0.75))
            keep = items[:keep_count]
            drop = items[keep_count:]
            for d in drop:
                await db.photos.update_one({"id": d["id"]}, {"$set": {"is_duplicate": True, "is_selected": False}})
            for k in keep:
                await db.photos.update_one({"id": k["id"]}, {"$set": {"is_duplicate": False, "is_selected": True}})
            selected.extend(keep)

        # Sort selected by group then by score
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

# ---------- PDF Export ----------
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

    # Cover template lookup (backend mirror of frontend palette)
    templates = {
        "teal-coral": {"bg": "#0F5A67", "accent": "#E56B55", "text": "#F9F8F6"},
        "sand-forest": {"bg": "#D5C9B3", "accent": "#2C402E", "text": "#1A1A17"},
        "navy-blush": {"bg": "#1C2D42", "accent": "#E8D5D1", "text": "#F9F8F6"},
        "terracotta-cream": {"bg": "#C05B3F", "accent": "#F5EBDC", "text": "#F9F8F6"},
        "forest-gold": {"bg": "#2C402E", "accent": "#C9A959", "text": "#F9F8F6"},
        "charcoal-rose": {"bg": "#2A2A28", "accent": "#D89A9E", "text": "#F9F8F6"},
    }
    tpl = templates.get(album.get("cover_template_id", "teal-coral"), templates["teal-coral"])
    cover = album.get("cover") or {}
    bg_color = cover.get("bg_color") or tpl["bg"]
    accent_color = cover.get("accent_color") or tpl["accent"]
    text_color = cover.get("text_color") or tpl["text"]

    def draw_text_item(item, page_w, page_h, default_color="#1A1A17"):
        """Draw a text item using its font_weight/font_style. Uses Helvetica family."""
        weight = str(item.get("font_weight", "normal")).lower()
        style = str(item.get("font_style", "normal")).lower()
        is_bold = weight in ("bold", "600", "700", "800", "900") or weight.isdigit() and int(weight) >= 600
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
            logger.error(f"Cover image draw failed: {e}")
    elif not cover.get("hide_illustration"):
        c.setFillColor(hex_to_rl_color(accent_color))
        c.circle(pw * 0.5, ph * 0.42, min(pw, ph) * 0.18, fill=1, stroke=0)

    # Extra items on cover (text / shape)
    for item in cover.get("extra_items", []) or []:
        it_type = item.get("type")
        if it_type == "text":
            draw_text_item(item, pw, ph, default_color=text_color)
        elif it_type == "shape":
            x = item["x"] * pw
            y_top = (1 - item["y"]) * ph
            slot_w = item["w"] * pw
            slot_h = item["h"] * ph
            y_bottom = y_top - slot_h
            c.setFillColor(hex_to_rl_color(item.get("fill_color", accent_color)))
            if item.get("shape_type") == "circle":
                c.ellipse(x, y_bottom, x + slot_w, y_bottom + slot_h, fill=1, stroke=0)
            else:
                c.rect(x, y_bottom, slot_w, slot_h, fill=1, stroke=0)
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
                    scale = float(item.get("scale", 1.0))
                    focal_x = float(item.get("focal_x", 0.5))
                    focal_y = float(item.get("focal_y", 0.5))
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
    c.setFont("Helvetica", min(pw, ph) * 0.04)
    country_text = album.get("country", "") or ""
    if country_text:
        c.drawCentredString(pw / 2, ph * 0.5, country_text.upper())
    c.setFont("Helvetica", min(pw, ph) * 0.025)
    c.drawCentredString(pw / 2, ph * 0.1, str(album.get("year", "")))
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
        {"id": "teal-coral", "name": "Océan Corail", "bg": "#0F5A67", "accent": "#E56B55", "text": "#F9F8F6", "illustration": "coral"},
        {"id": "sand-forest", "name": "Sable & Forêt", "bg": "#D5C9B3", "accent": "#2C402E", "text": "#1A1A17", "illustration": "leaf"},
        {"id": "navy-blush", "name": "Marine & Blush", "bg": "#1C2D42", "accent": "#E8D5D1", "text": "#F9F8F6", "illustration": "wave"},
        {"id": "terracotta-cream", "name": "Terracotta", "bg": "#C05B3F", "accent": "#F5EBDC", "text": "#F9F8F6", "illustration": "sun"},
        {"id": "forest-gold", "name": "Forêt & Or", "bg": "#2C402E", "accent": "#C9A959", "text": "#F9F8F6", "illustration": "mountain"},
        {"id": "charcoal-rose", "name": "Charbon & Rose", "bg": "#2A2A28", "accent": "#D89A9E", "text": "#F9F8F6", "illustration": "bird"},
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
