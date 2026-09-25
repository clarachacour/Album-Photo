"""Order statuses, print-ready PDF generation and post-order cleanup."""
import asyncio
import logging
import time as _time
from datetime import datetime, timedelta, timezone


from app.config import APP_NAME, FRONTEND_URL, MAX_CONCURRENT_PDF_GENERATIONS
from app.core.auth import create_token
from app.core.executors import (
    pdf_render_executor,
    photo_processing_executor,
    run_blocking,
)
from app.db import db
from app.services.email import (
    send_pdf_generation_failed_email,
    send_printer_order_email,
)
from app.services.pdf import render_album_pdf_sync
from app.services.photos import generate_print_variant, print_needs_conversion
from app.services.storage import delete_object, put_object

logger = logging.getLogger(__name__)


ORDER_STATUSES = ["pending_payment", "paid", "processing", "printing", "ready_for_delivery", "shipped", "delivered", "cancelled"]

# ---------- Orders ----------
ORDER_STATUS_LABELS = {
    "pending_payment": "Payment pending",
    "paid": "Payment confirmed",
    "processing": "Preparing your album",
    "printing": "Printing",
    "ready_for_delivery": "Ready for delivery",
    "shipped": "Shipped",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}
# The order in which a normal (non-cancelled) order is expected to progress —
# drives the tracking timeline on the frontend.
ORDER_STATUS_SEQUENCE = ["pending_payment", "paid", "processing", "printing", "ready_for_delivery", "shipped", "delivered"]

# (MAX_CONCURRENT_PDF_GENERATIONS is defined earlier, alongside the other
# concurrency constants, so pdf_render_executor's own worker count can be
# derived from it — see that definition's comment for the full reasoning.)
# If an instance ever crashes hard enough mid-generation that the
# `finally` block releasing its slot never runs (an OOM kill, say), that
# slot would otherwise sit "held" forever, permanently shrinking the
# effective limit by one. Generous on purpose — real generations,
# even a very large album needing many recursive retries, shouldn't
# legitimately take this long — but the goal is only to eventually
# self-heal from an abandoned slot, not to cut off a merely slow one.
PDF_GENERATION_SLOT_STALE_MINUTES = 45

async def purge_stale_pdf_generation_slots():
    """A slot only ever gets removed by _release_pdf_generation_slot, which
    runs in generate_order_pdf's finally block — fine for a normal
    success or a caught exception, but Cloud Run's own hard request
    timeout (3600s max) kills the process outright with no chance for any
    Python-level cleanup to run, so a generation that hits that ceiling
    leaves its slot behind forever otherwise. Previously this cleanup only
    ran inside _acquire_pdf_generation_slot, which meant a stale slot sat
    there — showing "Generating…" in the admin UI and, worse, still
    counting against MAX_CONCURRENT_PDF_GENERATIONS and blocking every
    other order from starting — until someone happened to attempt another
    generation, which is what let a single dead slot from days earlier
    quietly stall the whole queue. Called here too (from admin_list_orders)
    so just loading the admin page self-heals it, not only starting a new
    generation."""
    stale_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=PDF_GENERATION_SLOT_STALE_MINUTES)).isoformat()
    await db.pdf_generation_slots.delete_many({"started_at": {"$lt": stale_cutoff}})

async def _acquire_pdf_generation_slot(order_id: str):
    """Blocks (polling, not busy-waiting) until fewer than
    MAX_CONCURRENT_PDF_GENERATIONS are genuinely in progress service-wide,
    then claims one for this order. No overall timeout on the wait itself
    — a queued generation is expected to eventually get its turn rather
    than fail outright, matching "reliability over speed" for this
    specifically: a customer's order should never fail *just* because
    other customers happened to be ordering at the same moment."""
    while True:
        await purge_stale_pdf_generation_slots()
        active_count = await db.pdf_generation_slots.count_documents({})
        if active_count < MAX_CONCURRENT_PDF_GENERATIONS:
            try:
                await db.pdf_generation_slots.insert_one({"order_id": order_id, "started_at": datetime.now(timezone.utc).isoformat()})
                return
            except Exception:
                pass  # another request claimed the slot first (or a duplicate order_id) — just retry the check
        else:
            logger.info(f"Commande {order_id} : {active_count} génération(s) déjà en cours, en attente d'une place disponible…")
        await asyncio.sleep(15)

async def _release_pdf_generation_slot(order_id: str):
    await db.pdf_generation_slots.delete_many({"order_id": order_id})

async def generate_order_pdf(order_id: str, album_id: str, user_id: str):
    """Runs in the background right after an order is created. Reuses the
    exact same browser-based renderer as the (now customer-facing-removed)
    PDF export, so the file the team sends to the printer is guaranteed to
    match what the customer saw in the flipbook. Never surfaced to the
    customer directly — this is purely for internal/printer use."""
    t_start = _time.monotonic()
    await _acquire_pdf_generation_slot(order_id)
    try:
        album_doc = await db.albums.find_one({"id": album_id}, {"pages": 1})
        interior_pages = (album_doc or {}).get("pages", [])
        photo_ids = {
            it["photo_id"]
            for pg in interior_pages
            for it in (pg.get("items") or [])
            if it.get("type") == "photo" and it.get("photo_id")
        }
        # Photos are printed at the full resolution stored at upload. Only
        # formats a browser can't draw (HEIC…) need a JPEG copy, made here
        # up front so the page renders don't wait on conversions.
        if photo_ids:
            photos_list = await db.photos.find(
                {"id": {"$in": list(photo_ids)}, "user_id": user_id}, {"_id": 0}
            ).to_list(len(photo_ids))
            to_convert = [ph for ph in photos_list if print_needs_conversion(ph) and not ph.get("print_full_path")]
            loop = asyncio.get_event_loop()
            semaphore = asyncio.Semaphore(4)

            async def convert(photo):
                async with semaphore:
                    print_path, _ = await loop.run_in_executor(photo_processing_executor, generate_print_variant, photo)
                if print_path:
                    await db.photos.update_one({"id": photo["id"]}, {"$set": {"print_full_path": print_path}})

            await asyncio.gather(*(convert(ph) for ph in to_convert))

        token = create_token(user_id)
        print_url = f"{FRONTEND_URL}/print/{album_id}?auth={token}"
        loop = asyncio.get_event_loop()
        pdf_bytes = await loop.run_in_executor(
            pdf_render_executor, render_album_pdf_sync, print_url, len(interior_pages), f"Commande {order_id} :"
        )
        path = f"{APP_NAME}/orders/{order_id}.pdf"
        await run_blocking(put_object, path, pdf_bytes, "application/pdf")
        await db.orders.update_one({"id": order_id}, {"$set": {"pdf_path": path, "pdf_ready": True}})
        logger.info(f"Commande {order_id} : PDF complet généré en {_time.monotonic() - t_start:.1f}s au total")

        # Moved in from create_order/admin_regenerate_order_pdf: this
        # function now runs as a genuine background task (see both
        # callers), so nothing is left waiting around afterward to do
        # this — it has to happen here, right after the PDF is confirmed
        # ready, or it would never happen at all.
        order = await db.orders.find_one({"id": order_id}, {"_id": 0})
        if order and order["status"] not in ("printing", "ready_for_delivery", "shipped", "delivered"):
            now2 = datetime.now(timezone.utc).isoformat()
            await db.orders.update_one(
                {"id": order_id},
                {"$set": {"status": "printing", "updated_at": now2}, "$push": {"status_history": {"status": "printing", "at": now2}}},
            )
            order["status"] = "printing"
            send_printer_order_email(order)
            # Only a genuinely successful, first-time order — a real PDF a
            # printer will actually receive — has "the book is done,
            # unused photos can go" become true. Excluded from the status
            # check above on purpose: an admin regenerate on an
            # already-printing order shouldn't re-trigger this cleanup a
            # second time.
            await _delete_unselected_photos(album_id)
    except Exception as e:
        logger.error(f"Échec de la génération du PDF pour la commande {order_id}: {e}")
        await db.orders.update_one({"id": order_id}, {"$set": {"pdf_ready": False, "pdf_error": str(e)}})
        fresh_failed = await db.orders.find_one({"id": order_id}, {"_id": 0})
        if fresh_failed:
            send_pdf_generation_failed_email(fresh_failed, str(e))
    finally:
        await _release_pdf_generation_slot(order_id)

async def _delete_unselected_photos(album_id: str):
    """Runs right after an order actually succeeds (never on a failed
    attempt — see create_order, this used to fire unconditionally even
    when PDF generation failed, deleting photos from an order that never
    actually went anywhere). Deletes whichever of the album's photos
    aren't placed on any page — freeing R2 space for what the printed
    book genuinely never needed.

    Checks the album's *current* pages for which photo_ids are actually
    placed, rather than trusting each photo's stored is_selected flag —
    that flag is set once, when the AI first curates the album, and goes
    stale the moment someone manually drags a previously-rejected photo
    into a page afterward (or removes a previously-selected one). Only
    ever deletes a photo confirmed absent from every current page,
    regardless of what is_selected happens to say."""
    try:
        album = await db.albums.find_one({"id": album_id}, {"pages": 1})
        used_photo_ids = {
            it.get("photo_id")
            for pg in (album or {}).get("pages", [])
            for it in (pg.get("items") or [])
            if it.get("type") == "photo" and it.get("photo_id")
        }
        all_photos = await db.photos.find({"album_id": album_id, "is_deleted": False}, {"_id": 0}).to_list(5000)
        unused = [p for p in all_photos if p["id"] not in used_photo_ids]
        for p in unused:
            delete_object(p.get("storage_path"))
            delete_object(p.get("thumbnail_path"))
            delete_object(p.get("medium_path"))
            delete_object(p.get("print_path"))
            delete_object(p.get("print_full_path"))
        ids = [p["id"] for p in unused]
        if ids:
            await db.photos.update_many({"id": {"$in": ids}}, {"$set": {"is_deleted": True}})
    except Exception as e:
        logger.error(f"Échec du nettoyage des photos non sélectionnées pour l'album {album_id}: {e}")
