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
from app.schemas import CoverAssetFromPhotoInput, GooglePhotosImportInput
from app.services.cover_assets import store_cover_asset
from app.services.google_photos import download_google_item
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
    album = await _cover_album(album_id, user)
    return await store_cover_asset(album, file.filename, file.content_type, await file.read())

async def _cover_album(album_id: str, user: dict) -> dict:
    album = await db.albums.find_one({"id": album_id, **album_scope(user)})
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    await reject_if_ordered(album_id, user=user)
    return album

@router.post("/albums/{album_id}/cover-assets/from-photo")
async def cover_asset_from_photo(album_id: str, data: CoverAssetFromPhotoInput, user: dict = Depends(get_current_user)):
    """One of the album's own photos, put on the cover: copied as a cover
    image, so that deleting it from the album later leaves the cover as it is."""
    album = await _cover_album(album_id, user)
    photo = await db.photos.find_one({"id": data.photo_id, "album_id": album_id, "is_deleted": False}, {"_id": 0})
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    content, _ = await run_blocking(get_object, photo["storage_path"])
    return await store_cover_asset(album, photo.get("filename") or photo["storage_path"], photo.get("content_type"), content)

@router.post("/albums/{album_id}/cover-assets/google-photos")
async def cover_asset_from_google_photos(album_id: str, data: GooglePhotosImportInput, user: dict = Depends(get_current_user)):
    """The photo chosen in Google Photos' picker, put on the cover (the
    first one, if several were chosen)."""
    album = await _cover_album(album_id, user)
    filename, content_type, content = await download_google_item(data.items, data.access_token)
    return await store_cover_asset(album, filename, content_type, content)

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
