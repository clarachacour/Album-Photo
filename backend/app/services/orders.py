"""Order statuses, print-ready PDF generation and post-order cleanup."""
import asyncio
import logging
import time as _time
from datetime import datetime, timedelta, timezone


from app.config import APP_NAME, FRONTEND_URL, MAX_CONCURRENT_PDF_GENERATIONS
from app.core.auth import create_print_token
from app.core.executors import (
    pdf_render_executor,
    photo_processing_executor,
    run_blocking,
    run_email,
)
from app.db import db
from app.services.email import (
    send_digital_album_ready_email,
    send_pdf_generation_failed_email,
    send_printer_order_email,
)
from app.services.pdf import render_album_pdf_sync
from app.services.photos import generate_print_variant, print_needs_conversion
from app.services.storage import delete_object, put_object
from app.services.tasks import enqueue_order_pdf, pdf_tasks_enabled

logger = logging.getLogger(__name__)


ORDER_STATUSES = ["pending_payment", "paid", "processing", "printing", "ready_for_delivery", "shipped", "delivered", "available", "cancelled"]

# ---------- Orders ----------
ORDER_STATUS_LABELS = {
    "pending_payment": "Payment pending",
    "paid": "Payment confirmed",
    "processing": "Preparing your album",
    "printing": "Printing",
    "ready_for_delivery": "Ready for delivery",
    "shipped": "Shipped",
    "delivered": "Delivered",
    "available": "Ready to download",
    "cancelled": "Cancelled",
}
# The order in which a normal (non-cancelled) order is expected to progress —
# drives the tracking timeline on the frontend.
ORDER_STATUS_SEQUENCE = ["pending_payment", "paid", "processing", "printing", "ready_for_delivery", "shipped", "delivered"]
# A digital album (the PDF to download): made at once, but only handed over
# once the payment is confirmed ("paid", set by hand in the admin).
DIGITAL_STATUS_SEQUENCE = ["pending_payment", "paid", "available"]


def order_kind(order: dict) -> str:
    """"print" or "digital". Orders from before digital albums have no kind."""
    return order.get("kind") or "print"


def status_sequence(order: dict) -> list:
    return DIGITAL_STATUS_SEQUENCE if order_kind(order) == "digital" else ORDER_STATUS_SEQUENCE


async def deliver_digital_if_ready(order_id: str) -> bool:
    """Hands a digital album over — status "available" and the "ready to
    download" email — once it's both paid and made, whichever comes last.
    The email goes once. Returns True when handed over now."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order or order_kind(order) != "digital" or order.get("ready_email_sent_at"):
        return False
    if order["status"] not in ("paid", "available") or not order.get("pdf_ready"):
        return False
    now = datetime.now(timezone.utc).isoformat()
    claimed = await db.orders.update_one(
        {"id": order_id, "ready_email_sent_at": None},
        {"$set": {"ready_email_sent_at": now, "status": "available", "updated_at": now}},
    )
    if not claimed.modified_count:
        return False  # handed over meanwhile by another request
    if order["status"] != "available":
        await db.orders.update_one({"id": order_id}, {"$push": {"status_history": {"status": "available", "at": now}}})
    customer = await db.users.find_one({"id": order["user_id"]}, {"_id": 0})
    if customer:
        await run_email(send_digital_album_ready_email, customer.get("email"), customer.get("name"), {**order, "status": "available"})
    return True

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

async def start_order_pdf_generation(order: dict) -> bool:
    """Starts the order's PDF: through the Cloud Tasks queue when it's
    configured (returns True at once), otherwise right here, waiting for
    it (returns False when done). If the queue can't be reached, falls
    back to generating here rather than leaving the order without a PDF."""
    if pdf_tasks_enabled():
        try:
            await run_blocking(enqueue_order_pdf, order["id"])
            await db.orders.update_one({"id": order["id"]}, {"$set": {"pdf_queued_at": datetime.now(timezone.utc).isoformat()}})
            return True
        except Exception as e:
            logger.error(f"Commande {order['id']} : file Cloud Tasks injoignable ({e}), génération directe")
    await generate_order_pdf(order["id"], order["album_id"], order["user_id"])
    return False


async def generate_order_pdf(order_id: str, album_id: str, user_id: str, final_attempt: bool = True) -> bool:
    """Makes the order's print-ready PDF with the same browser renderer as
    the flipbook, so the printer gets exactly what the customer saw.
    Returns True on success. On failure the error is stored on the order;
    the admin is emailed only when final_attempt is True (the queue will
    try again otherwise)."""
    t_start = _time.monotonic()
    await _acquire_pdf_generation_slot(order_id)
    try:
        digital = order_kind(await db.orders.find_one({"id": order_id}, {"kind": 1}) or {}) == "digital"
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

        token = create_print_token(user_id, album_id)
        # A digital album: the pages as a reader sees them, photos in
        # screen quality (see PrintAlbum's digital mode).
        print_url = f"{FRONTEND_URL}/print/{album_id}?auth={token}{'&digital=1' if digital else ''}"
        loop = asyncio.get_event_loop()
        pdf_bytes = await loop.run_in_executor(
            pdf_render_executor, render_album_pdf_sync, print_url, len(interior_pages), f"Commande {order_id} :"
        )
        path = f"{APP_NAME}/orders/{order_id}.pdf"
        await run_blocking(put_object, path, pdf_bytes, "application/pdf")
        await db.orders.update_one({"id": order_id}, {"$set": {"pdf_path": path, "pdf_ready": True, "pdf_error": None}, "$unset": {"pdf_queued_at": ""}})
        logger.info(f"Commande {order_id} : PDF complet généré en {_time.monotonic() - t_start:.1f}s au total")

        # Moved in from create_order/admin_regenerate_order_pdf: this
        # function now runs as a genuine background task (see both
        # callers), so nothing is left waiting around afterward to do
        # this — it has to happen here, right after the PDF is confirmed
        # ready, or it would never happen at all.
        order = await db.orders.find_one({"id": order_id}, {"_id": 0})
        if digital:
            # No printer: handed to the customer once paid (see
            # deliver_digital_if_ready); the album's unused photos can go.
            if order and not order.get("ready_email_sent_at"):
                await _delete_unselected_photos(album_id)
            await deliver_digital_if_ready(order_id)
            return True
        if order and order["status"] not in ("printing", "ready_for_delivery", "shipped", "delivered"):
            now2 = datetime.now(timezone.utc).isoformat()
            await db.orders.update_one(
                {"id": order_id},
                {"$set": {"status": "printing", "updated_at": now2}, "$push": {"status_history": {"status": "printing", "at": now2}}},
            )
            order["status"] = "printing"
            await run_email(send_printer_order_email, order)
            # Only a genuinely successful, first-time order — a real PDF a
            # printer will actually receive — has "the book is done,
            # unused photos can go" become true. Excluded from the status
            # check above on purpose: an admin regenerate on an
            # already-printing order shouldn't re-trigger this cleanup a
            # second time.
            await _delete_unselected_photos(album_id)
        return True
    except Exception as e:
        logger.error(f"Échec de la génération du PDF pour la commande {order_id}{'' if final_attempt else ' (nouvel essai prévu)'} : {e}")
        update = {"$set": {"pdf_ready": False, "pdf_error": str(e)}}
        if final_attempt:
            update["$unset"] = {"pdf_queued_at": ""}
        await db.orders.update_one({"id": order_id}, update)
        if final_attempt:
            fresh_failed = await db.orders.find_one({"id": order_id}, {"_id": 0})
            if fresh_failed:
                await run_email(send_pdf_generation_failed_email, fresh_failed, str(e))
        return False
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
