"""A PDF of an album for the admin, with no order: nothing goes to the
printer, nothing is counted. In the format chosen here, whatever the one
chosen for orders (print_format): "bookstop" (the file sent to Bookstop
with an order) or "hardcover" (the one-sheet hardcover format). Kept as
<app>/test-pdfs/<album>.pdf (the latest one), its state on the album
(test_pdf: making / ready / failed)."""
import asyncio
import logging
from datetime import datetime, timezone

from app.config import APP_NAME, FRONTEND_URL
from app.core.auth import create_print_token
from app.core.executors import pdf_render_executor, run_blocking
from app.db import db
from app.services.orders import _acquire_pdf_generation_slot, _release_pdf_generation_slot, prepare_print_photos
from app.services.pdf import render_album_pdf_sync
from app.services.print_format import FORMATS, print_url_suffix
from app.services.storage import put_object

logger = logging.getLogger(__name__)


def test_pdf_path(album_id: str) -> str:
    return f"{APP_NAME}/test-pdfs/{album_id}.pdf"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def mark_making(album_id: str, fmt: str = "hardcover"):
    fmt = fmt if fmt in FORMATS else "hardcover"
    await db.albums.update_one({"id": album_id}, {"$set": {"test_pdf": {"status": "making", "format": fmt, "started_at": _now()}}})


async def make_test_pdf(album_id: str) -> bool:
    """Renders it (the album's pages as they are now) and stores it."""
    album = await db.albums.find_one({"id": album_id}, {"_id": 0, "user_id": 1, "pages": 1, "test_pdf": 1})
    if not album:
        return False
    # The format asked for (mark_making), also when made through the queue.
    fmt = (album.get("test_pdf") or {}).get("format") or "hardcover"
    slot = f"test-{album_id}"
    await _acquire_pdf_generation_slot(slot)
    try:
        pages = album.get("pages") or []
        await prepare_print_photos(pages, album["user_id"])
        token = create_print_token(album["user_id"], album_id)
        url = f"{FRONTEND_URL}/print/{album_id}?auth={token}{print_url_suffix(fmt, False)}"
        loop = asyncio.get_event_loop()
        pdf = await loop.run_in_executor(pdf_render_executor, render_album_pdf_sync, url, len(pages), f"PDF test {album_id} :")
        path = test_pdf_path(album_id)
        await run_blocking(put_object, path, pdf, "application/pdf")
        await db.albums.update_one({"id": album_id}, {"$set": {"test_pdf": {"status": "ready", "format": fmt, "path": path, "made_at": _now(), "pages": len(pages)}}})
        return True
    except Exception as e:
        logger.error(f"PDF test {album_id} : échec — {e}")
        await db.albums.update_one({"id": album_id}, {"$set": {"test_pdf": {"status": "failed", "format": fmt, "error": str(e)[:300], "made_at": _now()}}})
        return False
    finally:
        await _release_pdf_generation_slot(slot)
