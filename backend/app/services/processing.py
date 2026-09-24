"""Album processing pipeline: curation + layout, full or incremental."""
import logging
from datetime import datetime, timezone
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

        selected, curation_stats = await curate_photos(photos)
        orientation = album.get("orientation", "portrait") if album else "portrait"
        target_pages = album.get("target_pages", 50) if album else 50
        pages = [title_page] + deterministic_layout(selected, orientation, content_pages_budget=max(0, target_pages - 1))
        pages, fell_short = await trim_pages_to_target(pages, target_pages)

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

        newly_selected, curation_stats = await curate_photos(new_photos, existing_selected)

        album = await db.albums.find_one({"id": album_id}, {"_id": 0})
        orientation = album.get("orientation", "portrait") if album else "portrait"
        existing_pages = (album.get("pages") or []) if album else []
        start_idx = len(existing_pages) % len(LAYOUT_PATTERN)
        new_pages = deterministic_layout(newly_selected, orientation, pattern_start_idx=start_idx, content_pages_budget=max(0, (album.get("target_pages", 50) if album else 50) - 1 - max(0, len(existing_pages) - 1)))
        combined_pages = existing_pages + new_pages
        target_pages = album.get("target_pages", 50) if album else 50
        combined_pages, fell_short = await trim_pages_to_target(combined_pages, target_pages)

        await db.albums.update_one(
            {"id": album_id},
            {"$set": {"pages": combined_pages, "status": "ready", "pages_below_target": fell_short, "curation_stats": curation_stats, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        logger.info(f"Incremental AI processing complete for album {album_id}: +{len(newly_selected)} photos, +{len(new_pages)} pages")
    except Exception as e:
        logger.error(f"Incremental AI processing error: {e}")
        await db.albums.update_one({"id": album_id}, {"$set": {"status": "error"}})
