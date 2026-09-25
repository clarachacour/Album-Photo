"""Upload from a phone via a QR code (no login on the phone)."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.config import FRONTEND_URL
from app.core.auth import get_current_user
from app.db import db
from app.schemas import GooglePhotosImportInput, MobileUploadSessionOut, MobileUploadStatusInput
from app.services.albums import reject_if_ordered
from app.services.google_photos import import_google_photos_items
from app.services.photos import store_many_photos
from app.services.processing import run_ai_processing_incremental

router = APIRouter()


# ---------- Mobile upload (QR code) ----------
# Sessions used to live in an in-memory dict (_mobile_sessions), scoped to a
# single backend process. Cloud Run can run several instances at once, each
# with its own memory — the request that creates the session (from the
# logged-in browser) and the request that reads it (from the phone that
# scanned the QR code) can land on two different instances. When that
# happens the second instance has never heard of the token and reports it
# as "expired" seconds after it was created. Storing sessions in MongoDB
# instead makes them visible to every instance, exactly like
# pdf_generation_slots. A TTL index (see lifespan() in app/main.py) does the cleanup
# automatically.
MOBILE_UPLOAD_SESSION_HOURS = 1
# While it sends photos, the phone reports "uploading" again every 20 s
# (MobileUpload.jsx). Past this delay without news — phone locked, page
# closed mid-upload — the computer stops waiting for it.
PHONE_STATUS_STALE_SECONDS = 60

@router.post("/albums/{album_id}/mobile-upload-session", response_model=MobileUploadSessionOut)
async def create_mobile_upload_session(album_id: str, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    await reject_if_ordered(album_id)
    token = str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(hours=MOBILE_UPLOAD_SESSION_HOURS)
    await db.mobile_sessions.insert_one({
        "token": token,
        "album_id": album_id,
        "user_id": user["id"],
        "expires": expires,
    })
    return MobileUploadSessionOut(
        token=token,
        upload_url=f"{FRONTEND_URL}/mobile-upload/{token}",
        expires_at=expires.isoformat(),
    )

async def _get_mobile_session(token: str) -> dict:
    session = await db.mobile_sessions.find_one({"token": token})
    if not session:
        raise HTTPException(status_code=400, detail="This link has expired or is invalid")
    # Mongo/motor hands back naive datetimes (it strips the tzinfo on the
    # round-trip through BSON) even though we stored an aware UTC datetime.
    # Comparing a naive value against datetime.now(timezone.utc) (aware)
    # raises TypeError, which FastAPI turns into a 500 — the frontend then
    # shows the same "expired" message as a real expiry, which is why this
    # looked like the link dying seconds after being created. Re-attach UTC
    # before comparing instead of comparing raw.
    expires = session["expires"]
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="This link has expired or is invalid")
    return session

def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

@router.get("/albums/{album_id}/mobile-upload-session/{token}")
async def mobile_upload_session_status(album_id: str, token: str, user: dict = Depends(get_current_user)):
    """Whether the phone is still sending photos, so the computer can let
    the person move on as soon as it's done rather than guessing."""
    session = await db.mobile_sessions.find_one({"token": token, "album_id": album_id, "user_id": user["id"]})
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found")
    status_at = session.get("phone_status_at")
    fresh = status_at is not None and datetime.now(timezone.utc) - _aware(status_at) < timedelta(seconds=PHONE_STATUS_STALE_SECONDS)
    return {"uploading": bool(session.get("phone_uploading")) and fresh}

@router.post("/mobile-upload/{token}/status")
async def mobile_upload_status(token: str, data: MobileUploadStatusInput):
    """The phone says it started (and is still) sending photos, or is done."""
    session = await _get_mobile_session(token)
    await db.mobile_sessions.update_one(
        {"token": session["token"]},
        {"$set": {"phone_uploading": data.uploading, "phone_status_at": datetime.now(timezone.utc)}},
    )
    return {"ok": True}

@router.get("/mobile-upload/{token}/info")
async def mobile_upload_info(token: str):
    session = await _get_mobile_session(token)
    album = await db.albums.find_one({"id": session["album_id"]}, {"_id": 0, "title": 1})
    return {"album_id": session["album_id"], "album_title": (album or {}).get("title", "Album"), "expires_at": session["expires"].isoformat()}

@router.post("/mobile-upload/{token}/photos")
async def mobile_upload_photos(token: str, files: List[UploadFile] = File(...)):
    session = await _get_mobile_session(token)
    uploaded, limit_reached = await store_many_photos(session["album_id"], session["user_id"], files)

    if uploaded:
        album = await db.albums.find_one({"id": session["album_id"]}, {"_id": 0, "status": 1})
        # If the album has already been through its first AI pass (i.e. this
        # is "Add more photos" from the editor, not the initial creation
        # wizard), curate and append pages for these right away. During the
        # wizard, photos just land in the pool until "Start AI" is clicked.
        if album and album.get("status") == "ready":
            await db.albums.update_one({"id": session["album_id"]}, {"$set": {"status": "processing"}})
            # Awaited directly, not background-tasked — this used to be
            # background_tasks.add_task, the same pattern that Cloud Run
            # was found to silently kill mid-run for PDF generation (see
            # create_order's comment) — nothing here made it any safer just
            # because the work is AI curation instead of a PDF. A slower
            # response that reliably finishes beats a fast one that might
            # quietly never finish at all.
            await run_ai_processing_incremental(session["album_id"], session["user_id"], [p["id"] for p in uploaded])
    return {"uploaded": len(uploaded), "failed": len(files) - len(uploaded), "limit_reached": limit_reached}

@router.post("/mobile-upload/{token}/import/google-photos")
async def mobile_import_google_photos(token: str, data: GooglePhotosImportInput):
    """Same Google Photos import as import_google_photos above, but reached
    from the phone that scanned the QR code — authenticated by the mobile
    session token rather than a login, exactly like mobile_upload_photos.
    Lets someone on their phone pick straight from Google Photos (with
    Google's own picker UI and its per-album "select all", which the phone's
    generic OS file-source integration with the Google Photos app doesn't
    offer) instead of only their camera roll."""
    session = await _get_mobile_session(token)
    album_id = session["album_id"]
    uploaded, limit_reached = await import_google_photos_items(album_id, session["user_id"], data.items, data.access_token)

    if uploaded:
        album = await db.albums.find_one({"id": album_id}, {"_id": 0, "status": 1})
        if album and album.get("status") == "ready":
            await db.albums.update_one({"id": album_id}, {"$set": {"status": "processing"}})
            await run_ai_processing_incremental(album_id, session["user_id"], [p["id"] for p in uploaded])

    return {"uploaded": len(uploaded), "failed": len(data.items) - len(uploaded), "limit_reached": limit_reached}
