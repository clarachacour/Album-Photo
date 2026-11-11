"""A test PDF of an album in the one-sheet hardcover format, for the admin
to send a printer — whatever the format chosen for orders (print_format),
with no order: nothing goes to the printer, nothing is counted. Kept as
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
from app.services.storage import put_object

logger = logging.getLogger(__name__)


def test_pdf_path(album_id: str) -> str:
    return f"{APP_NAME}/test-pdfs/{album_id}.pdf"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def mark_making(album_id: str):
    await db.albums.update_one({"id": album_id}, {"$set": {"test_pdf": {"status": "making", "started_at": _now()}}})


async def make_test_pdf(album_id: str) -> bool:
    """Renders it (the album's pages as they are now) and stores it."""
    album = await db.albums.find_one({"id": album_id}, {"_id": 0, "user_id": 1, "pages": 1})
    if not album:
        return False
    slot = f"test-{album_id}"
    await _acquire_pdf_generation_slot(slot)
    try:
        pages = album.get("pages") or []
        await prepare_print_photos(pages, album["user_id"])
        token = create_print_token(album["user_id"], album_id)
        url = f"{FRONTEND_URL}/print/{album_id}?auth={token}&format=hardcover"
        loop = asyncio.get_event_loop()
        pdf = await loop.run_in_executor(pdf_render_executor, render_album_pdf_sync, url, len(pages), f"PDF test {album_id} :")
        path = test_pdf_path(album_id)
        await run_blocking(put_object, path, pdf, "application/pdf")
        await db.albums.update_one({"id": album_id}, {"$set": {"test_pdf": {"status": "ready", "path": path, "made_at": _now(), "pages": len(pages)}}})
        return True
    except Exception as e:
        logger.error(f"PDF test {album_id} : échec — {e}")
        await db.albums.update_one({"id": album_id}, {"$set": {"test_pdf": {"status": "failed", "error": str(e)[:300], "made_at": _now()}}})
        return False
    finally:
        await _release_pdf_generation_slot(slot)
