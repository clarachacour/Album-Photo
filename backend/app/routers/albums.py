"""Album routes: CRUD, processing, page repacking, PDF export."""
import asyncio
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import Response

from app.config import DRAFT_ALBUM_RETENTION_DAYS, FRONTEND_URL
from app.core.auth import decode_token, get_current_user
from app.db import db
from app.schemas import AlbumCreate, AlbumUpdate, RepackPagesInput
from app.services.albums import reject_if_ordered
from app.services.layout import (
    LAYOUT_PATTERN,
    TEMPLATE_PHOTO_COUNT,
    deterministic_layout,
    make_title_page,
)
from app.services.pdf import render_pdf_via_browser_sync
from app.services.pdf_legacy import export_pdf_reportlab_legacy
from app.services.photos import store_many_photos
from app.services.processing import (
    run_ai_processing,
    run_ai_processing_incremental,
    trim_pages_to_target,
)
from app.services.storage import delete_object

logger = logging.getLogger(__name__)
router = APIRouter()


ALLOWED_ALBUM_SIZES = {"A4", "A5"}

@router.post("/albums")
async def create_album(data: AlbumCreate, user: dict = Depends(get_current_user)):
    if data.size not in ALLOWED_ALBUM_SIZES:
        # A3 was removed — it exceeds the printing office's max open (flat)
        # hardcover size in both orientations, so an A3 album could never
        # actually be printed. This also catches any other unsupported
        # value, not just A3 specifically.
        raise HTTPException(status_code=400, detail=f"Unsupported album size — choose one of: {', '.join(sorted(ALLOWED_ALBUM_SIZES))}")
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
        "pages": [make_title_page(data.title, data.lang)],
        "cover_image_path": None,
        "cover": data.cover or {},
        "created_at": now,
        "updated_at": now,
    }
    await db.albums.insert_one(album)
    album.pop("_id", None)
    return album

@router.get("/albums")
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

@router.get("/albums/{album_id}")
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
    # Lets the editor show a clear "this album is locked" state and disable
    # its controls up front, instead of the person only finding out via a
    # 403 the moment they try to save an edit (see reject_if_ordered,
    # which is the actual enforcement — this is just so the UI can match).
    # admin_unlocked has to be factored in here too, or the UI would keep
    # showing the album as locked even after reject_if_ordered has been
    # told to allow edits on it — the two would disagree.
    has_order = await db.orders.find_one({"album_id": album_id}) is not None
    album["was_ordered"] = has_order and not album.get("admin_unlocked")
    return album

@router.patch("/albums/{album_id}")
async def update_album(album_id: str, data: AlbumUpdate, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")
    await reject_if_ordered(album_id)
    if data.size is not None and data.size not in ALLOWED_ALBUM_SIZES:
        raise HTTPException(status_code=400, detail=f"Unsupported album size — choose one of: {', '.join(sorted(ALLOWED_ALBUM_SIZES))}")
    update = {k: v for k, v in data.model_dump(exclude_none=True).items()}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.albums.update_one({"id": album_id}, {"$set": update})
    updated = await db.albums.find_one({"id": album_id}, {"_id": 0})
    return updated

@router.delete("/albums/{album_id}")
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

@router.post("/albums/{album_id}/repack-pages")
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
    await reject_if_ordered(album_id)
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
        # album), trim_pages_to_target alone wouldn't actually add
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
            final_pages, _ = await trim_pages_to_target(pages, data.target_pages)
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


@router.post("/albums/{album_id}/process")
async def start_processing(album_id: str, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")
    await reject_if_ordered(album_id)
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

@router.get("/albums/{album_id}/status")
async def get_status(album_id: str, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": album_id, "user_id": user["id"]}, {"_id": 0, "status": 1, "id": 1, "google_import_result": 1})
    if not album:
        raise HTTPException(status_code=404, detail="Album introuvable")
    return {"status": album.get("status", "draft"), "google_import_result": album.get("google_import_result")}

@router.post("/albums/{album_id}/add-photos")
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
    await reject_if_ordered(album_id)

    uploaded, limit_reached = await store_many_photos(album_id, user["id"], files)
    new_ids = [p["id"] for p in uploaded]

    if not new_ids:
        raise HTTPException(status_code=400, detail="Aucune photo valide n'a pu être ajoutée")

    await db.albums.update_one({"id": album_id}, {"$set": {"status": "processing"}})
    # Awaited, not background-tasked — same throttling issue as
    # /albums/{id}/process (see its comment).
    await run_ai_processing_incremental(album_id, user["id"], new_ids)
    fresh = await db.albums.find_one({"id": album_id}, {"_id": 0, "status": 1})
    return {"status": fresh.get("status", "ready") if fresh else "ready", "added": len(new_ids), "limit_reached": limit_reached}

@router.get("/albums/{album_id}/export")
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
        pdf_bytes = await loop.run_in_executor(None, render_pdf_via_browser_sync, print_url)
        filename = f"{album.get('title', 'album').replace(' ', '_')}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"Browser-based PDF export failed, falling back to reportlab: {e}")
        return await export_pdf_reportlab_legacy(album_id=album_id, auth=auth, authorization=authorization)
