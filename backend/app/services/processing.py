"""Album processing pipeline: curation + layout, full or incremental.

One layout run at a time per album. Photos added to an album that has
already been laid out (from the computer, the phone or Google Photos, often
several batches at once) are marked layout_pending, and whichever request
holds the album's layout lock places every pending photo — including the
ones that arrive while it runs — before letting go. Without this, batches
processed side by side each read the pages, appended their own and saved:
the last one erased the others' pages, and batches arriving while the album
said "processing" were never laid out at all.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List

from app.db import db
from app.services.curation import curate_photos
from app.services.layout import LAYOUT_PATTERN, deterministic_layout, make_title_page

logger = logging.getLogger(__name__)


async def trim_pages_to_target(pages: List[dict], target_pages: int) -> tuple:
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

# A lock older than this belonged to a run that died (server restarted
# mid-way): the next request takes over. A live run refreshes it between rounds.
LAYOUT_LOCK_STALE_MINUTES = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _claim_layout(album_id: str) -> bool:
    """Takes the album's layout lock (and shows it as processing); False if
    another live run already holds it."""
    stale = (datetime.now(timezone.utc) - timedelta(minutes=LAYOUT_LOCK_STALE_MINUTES)).isoformat()
    res = await db.albums.update_one(
        {"id": album_id, "$or": [{"layout_lock": None}, {"layout_lock": {"$lt": stale}}]},
        {"$set": {"layout_lock": _now(), "status": "processing"}},
    )
    return res.modified_count == 1


async def _release_layout(album_id: str, status: str):
    await db.albums.update_one({"id": album_id}, {"$set": {"status": status}, "$unset": {"layout_lock": ""}})


async def _pending_photo_ids(album_id: str) -> List[str]:
    docs = await db.photos.find({"album_id": album_id, "layout_pending": True, "is_deleted": False}, {"_id": 0, "id": 1}).to_list(5000)
    return [d["id"] for d in docs]


def _placed_photo_ids(pages: List[dict]) -> set:
    return {it.get("photo_id") for pg in pages for it in (pg.get("items") or []) if it.get("type") == "photo" and it.get("photo_id")}


async def run_ai_processing(album_id: str, user_id: str) -> bool:
    """Analyze all the album's photos, mark duplicates, generate the layout
    from scratch. The album's first page (title page) is always preserved
    as-is — whatever the user already has there, edited or still the
    default — only the pages after it are (re)generated from the photos.
    Returns False (doing nothing) when a layout run is already going on."""
    if not await _claim_layout(album_id):
        logger.warning(f"Album {album_id}: mise en page déjà en cours, nouvelle demande ignorée")
        return False
    status = "ready"
    try:
        album = await db.albums.find_one({"id": album_id}, {"_id": 0})
        existing_pages = (album.get("pages") or []) if album else []
        title_page = existing_pages[0] if existing_pages else make_title_page(album.get("title") if album else None)

        photos = await db.photos.find({"album_id": album_id, "is_deleted": False}, {"_id": 0}).to_list(5000)
        if not photos:
            await db.albums.update_one({"id": album_id}, {"$set": {"pages": [title_page]}})
            return True

        selected, curation_stats = await curate_photos(photos)
        orientation = album.get("orientation", "portrait") if album else "portrait"
        target_pages = album.get("target_pages", 50) if album else 50
        pages = [title_page] + deterministic_layout(selected, orientation, content_pages_budget=max(0, target_pages - 1))
        pages, fell_short = await trim_pages_to_target(pages, target_pages)

        await db.albums.update_one(
            {"id": album_id},
            {"$set": {"pages": pages, "pages_below_target": fell_short, "curation_stats": curation_stats, "updated_at": _now()}}
        )
        # Every photo there was is laid out: none is waiting any more.
        await db.photos.update_many({"id": {"$in": [p["id"] for p in photos]}}, {"$unset": {"layout_pending": ""}})
        logger.info(
            f"AI processing complete for album {album_id}: {curation_stats.get('total_in')} photos in "
            f"→ {curation_stats.get('duplicates_removed')} duplicates removed, "
            f"{curation_stats.get('low_sharpness_removed')} rejected for low sharpness, "
            f"{curation_stats.get('redundant_removed')} thinned as visually redundant, "
            f"{curation_stats.get('ai_calls_attempted')} ambiguous clusters sent to AI, "
            f"{curation_stats.get('ai_clusters_resolved')} split by AI "
            f"({curation_stats.get('ai_photos_recovered')} extra photos recovered), "
            f"{curation_stats.get('faces_detected')} photos with a detected face (crop centered on it), "
            f"{len(selected)} selected, {len(pages)} pages"
        )
    except Exception as e:
        logger.error(f"AI processing error: {e}")
        status = "error"
    finally:
        await _release_layout(album_id, status)
    # Photos added while this ran (from the phone, say).
    await process_pending_photos(album_id, user_id)
    return True


async def add_photos_to_layout(album_id: str, user_id: str, photo_ids: List[str]):
    """For every way of adding photos to an album that has already been laid
    out: marks them as waiting, then lays out everything waiting — unless
    another request is already doing it, in which case that one will."""
    if photo_ids:
        await db.photos.update_many({"id": {"$in": photo_ids}, "album_id": album_id}, {"$set": {"layout_pending": True}})
    await process_pending_photos(album_id, user_id)


async def process_pending_photos(album_id: str, user_id: str):
    """Appends pages for every photo waiting to be laid out, one layout run
    at a time per album (see the module docstring)."""
    # Checked again after letting go of the lock: a photo marked as waiting
    # just before the release would otherwise wait for the next addition.
    while await _pending_photo_ids(album_id):
        if not await _claim_layout(album_id):
            return  # a live run holds the lock: it will lay them out
        status = "ready"
        try:
            while True:
                ids = await _pending_photo_ids(album_id)
                if not ids:
                    break
                await db.albums.update_one({"id": album_id}, {"$set": {"layout_lock": _now()}})  # still alive
                try:
                    await _append_pages(album_id, ids)
                except Exception as e:
                    logger.error(f"Incremental AI processing error: {e}")
                    status = "error"
                # Laid out, or given up on (still in the album's photos, to place by hand).
                await db.photos.update_many({"id": {"$in": ids}}, {"$unset": {"layout_pending": ""}})
                if status == "error":
                    break
        finally:
            await _release_layout(album_id, status)
        if status == "error":
            return


async def _append_pages(album_id: str, new_photo_ids: List[str]):
    """Curates only the given photos (checking them for duplicates against
    what's already in the album too) and APPENDS new pages at the end —
    existing pages are left exactly as the user edited them. Only called
    while holding the album's layout lock."""
    album = await db.albums.find_one({"id": album_id}, {"_id": 0})
    existing_pages = (album.get("pages") or []) if album else []
    already_placed = _placed_photo_ids(existing_pages)
    new_photos = await db.photos.find(
        {"id": {"$in": new_photo_ids}, "is_deleted": False}, {"_id": 0}
    ).to_list(5000)
    new_photos = [p for p in new_photos if p["id"] not in already_placed]
    if not new_photos:
        return

    existing_selected = await db.photos.find(
        {"album_id": album_id, "is_deleted": False, "is_selected": True, "id": {"$nin": new_photo_ids}},
        {"_id": 0},
    ).to_list(5000)

    newly_selected, curation_stats = await curate_photos(new_photos, existing_selected)

    orientation = album.get("orientation", "portrait") if album else "portrait"
    target_pages = album.get("target_pages", 50) if album else 50
    start_idx = len(existing_pages) % len(LAYOUT_PATTERN)
    new_pages = deterministic_layout(newly_selected, orientation, pattern_start_idx=start_idx, content_pages_budget=max(0, target_pages - 1 - max(0, len(existing_pages) - 1)))
    combined_pages, fell_short = await trim_pages_to_target(existing_pages + new_pages, target_pages)

    await db.albums.update_one(
        {"id": album_id},
        {"$set": {"pages": combined_pages, "pages_below_target": fell_short, "curation_stats": curation_stats, "updated_at": _now()}}
    )
    logger.info(f"Incremental AI processing complete for album {album_id}: +{len(newly_selected)} photos, +{len(new_pages)} pages")
