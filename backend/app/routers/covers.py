"""Cover image and cover element assets."""
import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response

from app.config import APP_NAME
from app.core.auth import album_scope, decode_token_for_album, get_current_user, is_admin_id, token_claims
from app.core.executors import run_blocking
from app.db import db
from app.services.albums import reject_if_ordered
from app.services.photos import ALLOWED_MIME, cover_asset_medium, store_image_with_thumbnail
from app.services.storage import get_object

router = APIRouter()


# ---------- Cover image upload ----------
@router.post("/albums/{album_id}/cover-image")
async def upload_cover_image(
    album_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    await reject_if_ordered(album_id)
    content_type = file.content_type or "image/jpeg"
    if content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Unsupported image format")
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    ext = (file.filename or "cover.jpg").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"
    path = f"{APP_NAME}/users/{user['id']}/albums/{album_id}/cover-{uuid.uuid4()}.{ext}"
    loop = asyncio.get_event_loop()
    result, thumb_path, _, _ = await loop.run_in_executor(None, store_image_with_thumbnail, path, data, content_type)
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

@router.delete("/albums/{album_id}/cover-image")
async def remove_cover_image(album_id: str, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    await reject_if_ordered(album_id)
    await db.albums.update_one(
        {"id": album_id},
        {"$set": {"cover_image_path": None, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"ok": True}

@router.get("/albums/{album_id}/cover-image")
async def get_cover_image(album_id: str, auth: str = Query(None), authorization: str = Header(None), variant: str = Query("thumb")):
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    elif auth:
        token = auth
    user_id = decode_token_for_album(token, album_id) if token else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    scope = {} if await is_admin_id(user_id) else {"user_id": user_id}
    album = await db.albums.find_one({"id": album_id, **scope})
    if not album or not album.get("cover_image_path"):
        raise HTTPException(status_code=404, detail="No custom cover")
    path = album["cover_image_path"]
    served_content_type = album.get("cover_image_content_type")
    if variant == "thumb" and album.get("cover_image_thumbnail_path"):
        path = album["cover_image_thumbnail_path"]
        served_content_type = "image/jpeg"
    data, ctype = await run_blocking(get_object, path)
    return Response(content=data, media_type=served_content_type or ctype)

# ---------- Cover element assets (logo / added images on the cover) ----------
@router.post("/albums/{album_id}/cover-assets")
async def upload_cover_asset(album_id: str, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, **album_scope(user)})
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    await reject_if_ordered(album_id, user=user)
    content_type = file.content_type or "image/png"
    if content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Unsupported image format")
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    ext = (file.filename or "asset.png").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "png"
    asset_id = str(uuid.uuid4())
    # Kept with the album owner's files (the admin may be adding it to a
    # customer's cover): the print page, which opens the album as its owner,
    # can then read it.
    path = f"{APP_NAME}/users/{album['user_id']}/albums/{album_id}/cover-assets/{asset_id}.{ext}"
    loop = asyncio.get_event_loop()
    result, thumb_path, _, _ = await loop.run_in_executor(None, store_image_with_thumbnail, path, data, content_type)
    return {"storage_path": result["path"], "thumbnail_path": thumb_path}

@router.get("/cover-assets/image")
async def get_cover_asset_image(path: str = Query(...), auth: str = Query(None), authorization: str = Header(None), variant: str = Query("thumb")):
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    elif auth:
        token = auth
    claims = token_claims(token) if token else None
    if not claims:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = claims["user_id"]
    # Safety: only serve assets that belong to the requesting user (and,
    # for a print key, to its album) — or any, to the admin signed in.
    if ".." in path:
        raise HTTPException(status_code=403, detail="Access denied")
    admin = claims["album_id"] is None and await is_admin_id(user_id)
    if f"/users/{user_id}/" not in path and not admin:
        raise HTTPException(status_code=403, detail="Access denied")
    if claims["album_id"] and f"/users/{user_id}/albums/{claims['album_id']}/" not in path:
        raise HTTPException(status_code=403, detail="Access denied")
    # Each asset has its own file name and never changes: the browser can
    # keep it for good instead of downloading it at every visit.
    cache = {"Cache-Control": "private, max-age=31536000, immutable"}
    if variant == "thumb" and not path.endswith("_thumb.jpg"):
        candidate = path.rsplit(".", 1)[0] + "_thumb.jpg"
        try:
            data, ctype = await run_blocking(get_object, candidate)
            return Response(content=data, media_type="image/jpeg", headers=cache)
        except Exception:
            pass  # no thumbnail on disk (asset predates this change, or generation failed) — fall back to original
    if variant == "medium":
        # Covers on screen ("My albums", the editor): a lighter copy made
        # once, instead of the full-resolution file kept for printing.
        data = await run_blocking(cover_asset_medium, path)
        if data:
            return Response(content=data, media_type="image/webp", headers=cache)
    data, ctype = await run_blocking(get_object, path)
    return Response(content=data, media_type=ctype, headers=cache)
