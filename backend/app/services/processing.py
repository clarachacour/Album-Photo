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
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import List

from app.core.executors import run_blocking
from app.db import db
from app.services.curation import curate_photos
from app.services.layout import LAYOUT_PATTERN, deterministic_layout, make_title_page
from app.services.tasks import enqueue_album_layout, pdf_tasks_enabled

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

# A live run refreshes its lock every LAYOUT_HEARTBEAT_SECONDS. A lock not
# refreshed for LAYOUT_LOCK_STALE_SECONDS belonged to a run that died (server
# restarted, request cut off by a timeout): the next request takes over, and
# an album left showing "processing" is started again (see rescue_layout).
LAYOUT_HEARTBEAT_SECONDS = 30
LAYOUT_LOCK_STALE_SECONDS = 180


def version_query(version: int) -> dict:
    """Matches an album still at this version (albums from before versions
    existed count as version 0)."""
    if version == 0:
        return {"$or": [{"version": 0}, {"version": {"$exists": False}}]}
    return {"version": version}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stale_before() -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=LAYOUT_LOCK_STALE_SECONDS)).isoformat()


async def _claim_layout(album_id: str) -> bool:
    """Takes the album's layout lock (and shows it as processing); False if
    another live run already holds it."""
    res = await db.albums.update_one(
        {"id": album_id, "$or": [{"layout_lock": None}, {"layout_lock": {"$lt": _stale_before()}}]},
        {"$set": {"layout_lock": _now(), "status": "processing"}},
    )
    return res.modified_count == 1


async def _release_layout(album_id: str, status: str):
    await db.albums.update_one({"id": album_id}, {"$set": {"status": status}, "$unset": {"layout_lock": ""}})


@asynccontextmanager
async def _heartbeat(album_id: str):
    """Keeps the lock fresh while the work goes on, so it's never mistaken
    for a dead run however long a large album takes."""
    async def beat():
        while True:
            await asyncio.sleep(LAYOUT_HEARTBEAT_SECONDS)
            try:
                await db.albums.update_one({"id": album_id, "layout_lock": {"$ne": None}}, {"$set": {"layout_lock": _now()}})
            except Exception as e:
                logger.warning(f"Album {album_id}: verrou de mise en page non rafraîchi ({e})")

    task = asyncio.create_task(beat())
    try:
        yield
    finally:
        task.cancel()


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
        async with _heartbeat(album_id):
            await _full_layout(album_id)
    except Exception as e:
        logger.error(f"AI processing error: {e}")
        status = "error"
    finally:
        await db.albums.update_one({"id": album_id}, {"$unset": {"layout_full_pending": ""}})
        await _release_layout(album_id, status)
    # Photos added while this ran (from the phone, say).
    await process_pending_photos(album_id, user_id)
    return True


async def _full_layout(album_id: str):
    album = await db.albums.find_one({"id": album_id}, {"_id": 0})
    existing_pages = (album.get("pages") or []) if album else []
    title_page = existing_pages[0] if existing_pages else make_title_page(album.get("title") if album else None)

    photos = await db.photos.find({"album_id": album_id, "is_deleted": False}, {"_id": 0}).to_list(5000)
    if not photos:
        await db.albums.update_one({"id": album_id}, {"$set": {"pages": [title_page]}, "$inc": {"version": 1}})
        return

    selected, curation_stats = await curate_photos(photos)
    orientation = album.get("orientation", "portrait") if album else "portrait"
    target_pages = album.get("target_pages", 50) if album else 50
    pages = [title_page] + deterministic_layout(selected, orientation, content_pages_budget=max(0, target_pages - 1))
    pages, fell_short = await trim_pages_to_target(pages, target_pages)

    await db.albums.update_one(
        {"id": album_id},
        {"$set": {"pages": pages, "pages_below_target": fell_short, "curation_stats": curation_stats, "updated_at": _now()}, "$inc": {"version": 1}},
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


async def start_full_layout(album_id: str, user_id: str) -> bool:
    """The album's first layout, asked for at the end of its creation.
    Through the Cloud Tasks queue when there is one (returns True at once:
    the page then follows the album's status), otherwise right here,
    waiting for it (returns False when done)."""
    await db.albums.update_one(
        {"id": album_id},
        {"$set": {"status": "processing", "layout_full_pending": True, "layout_requested_at": _now()}},
    )
    if pdf_tasks_enabled():
        try:
            await run_blocking(enqueue_album_layout, album_id)
            return True
        except Exception as e:
            logger.error(f"Album {album_id} : file Cloud Tasks injoignable ({e}), mise en page directe")
    await run_ai_processing(album_id, user_id)
    return False


async def resume_layout(album_id: str, user_id: str):
    """Does whatever layout the album is still waiting for: the full one if
    it never finished, otherwise the photos still pending. Called by the
    queue, and to restart a run that died."""
    album = await db.albums.find_one({"id": album_id}, {"_id": 0, "id": 1, "layout_full_pending": 1})
    if album is None:
        return
    if album.get("layout_full_pending"):
        await run_ai_processing(album_id, user_id)
        return
    await process_pending_photos(album_id, user_id)
    # A run that died after saving its work: nothing is left to do.
    await db.albums.update_one(
        {"id": album_id, "status": "processing", "$or": [{"layout_lock": None}, {"layout_lock": {"$lt": _stale_before()}}]},
        {"$set": {"status": "ready"}, "$unset": {"layout_lock": ""}},
    )


async def rescue_layout(album: dict) -> bool:
    """An album showing "processing" whose run died (server restarted,
    request cut off): starts it again, once. Called while someone is
    looking at the album (its status is polled), so nobody is left in front
    of an endless "creating your album". Returns True when restarted."""
    if album.get("status") != "processing":
        return False
    stale = _stale_before()
    if max(album.get("layout_lock") or "", album.get("layout_requested_at") or "") >= stale:
        return False  # a run is alive, or was just asked for
    # Several polls may see it at once: only the one that marks it restarts it.
    res = await db.albums.update_one(
        {
            "id": album["id"],
            "status": "processing",
            "$and": [
                {"$or": [{"layout_lock": None}, {"layout_lock": {"$lt": stale}}]},
                {"$or": [{"layout_requested_at": None}, {"layout_requested_at": {"$lt": stale}}]},
            ],
        },
        {"$set": {"layout_requested_at": _now()}},
    )
    if res.modified_count != 1:
        return False
    logger.warning(f"Album {album['id']} : mise en page interrompue, relancée")
    if pdf_tasks_enabled():
        try:
            await run_blocking(enqueue_album_layout, album["id"])
            return True
        except Exception as e:
            logger.error(f"Album {album['id']} : file Cloud Tasks injoignable ({e}), mise en page directe")
    await resume_layout(album["id"], album["user_id"])
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
        status = "error"
        try:
            async with _heartbeat(album_id):
                status = await _lay_out_pending(album_id)
        finally:
            await _release_layout(album_id, status)
        if status == "error":
            return


async def _lay_out_pending(album_id: str) -> str:
    """Places the pending photos, round after round, until none is left.
    Returns the album's status afterwards."""
    while True:
        ids = await _pending_photo_ids(album_id)
        if not ids:
            return "ready"
        failed = False
        try:
            await _append_pages(album_id, ids)
        except Exception as e:
            logger.error(f"Incremental AI processing error: {e}")
            failed = True
        # Laid out, or given up on (still in the album's photos, to place by hand).
        await db.photos.update_many({"id": {"$in": ids}}, {"$unset": {"layout_pending": ""}})
        if failed:
            return "error"


async def _append_pages(album_id: str, new_photo_ids: List[str]):
    """Curates only the given photos (checking them for duplicates against
    what's already in the album too) and APPENDS new pages at the end —
    existing pages are left exactly as the user edited them. Only called
    while holding the album's layout lock.

    The person may save edits while the photos are being sorted: the new
    pages are then added again onto the album as just saved, never onto
    the copy read before (which would erase those edits)."""
    new_photos = await db.photos.find(
        {"id": {"$in": new_photo_ids}, "is_deleted": False}, {"_id": 0}
    ).to_list(5000)
    album = await db.albums.find_one({"id": album_id}, {"_id": 0})
    new_photos = [p for p in new_photos if p["id"] not in _placed_photo_ids((album or {}).get("pages") or [])]
    if not album or not new_photos:
        return

    existing_selected = await db.photos.find(
        {"album_id": album_id, "is_deleted": False, "is_selected": True, "id": {"$nin": new_photo_ids}},
        {"_id": 0},
    ).to_list(5000)

    newly_selected, curation_stats = await curate_photos(new_photos, existing_selected)

    for _ in range(5):
        existing_pages = album.get("pages") or []
        already_placed = _placed_photo_ids(existing_pages)
        to_place = [p for p in newly_selected if p["id"] not in already_placed]
        orientation = album.get("orientation", "portrait")
        target_pages = album.get("target_pages", 50)
        start_idx = len(existing_pages) % len(LAYOUT_PATTERN)
        new_pages = deterministic_layout(to_place, orientation, pattern_start_idx=start_idx, content_pages_budget=max(0, target_pages - 1 - max(0, len(existing_pages) - 1)))
        combined_pages, fell_short = await trim_pages_to_target(existing_pages + new_pages, target_pages)
        # The album keeps the page count the person chose: photos that don't fit
        # stay in "All your photos", and the editor says so (unplaced_added).
        placed = _placed_photo_ids(combined_pages)
        unplaced = [p["id"] for p in to_place if p["id"] not in placed]

        res = await db.albums.update_one(
            {"id": album_id, **version_query(album.get("version", 0))},
            {"$set": {
                "pages": combined_pages, "pages_below_target": fell_short, "curation_stats": curation_stats, "updated_at": _now(),
                "unplaced_added": len(unplaced), "unplaced_added_at": _now(),
            }, "$inc": {"version": 1}},
        )
        if res.matched_count:
            break
        album = await db.albums.find_one({"id": album_id}, {"_id": 0})
        if not album:
            return
    else:
        raise RuntimeError("the album kept changing while its new pages were being added")
    logger.info(f"Incremental AI processing complete for album {album_id}: +{len(newly_selected)} photos, +{len(new_pages)} pages")
