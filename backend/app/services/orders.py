"""Order statuses, print-ready PDF generation and post-order cleanup."""
import asyncio
import gc
import logging
import time as _time
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import List

from pypdf import PdfReader, PdfWriter

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
from app.services.pdf import render_pdf_via_browser_sync
from app.services.photos import generate_print_variant
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
        # Pre-warm every used photo's "print" variant BEFORE launching the
        # browser. Without this, the headless browser (once it navigates
        # to the print page) requests every photo's print variant at
        # once — the first time any of them is needed, each of those
        # ~dozens of concurrent requests triggers its own resize+R2
        # upload, all competing for this same small instance's limited
        # thread pool alongside the PDF task itself waiting on the whole
        # page to finish loading. That self-inflicted contention was
        # stalling the export badly enough to run into the request
        # timeout with no clean error ever logged.
        #
        # Was strictly one photo at a time on the default pool — safe, but
        # needlessly slow: a large album (150-200+ used photos) pre-warming
        # sequentially, each paying its own full R2-fetch + resize +
        # R2-upload round trip, could easily take several minutes on its
        # own before Chromium even launches — and a generation that
        # measurably needed over an hour total for one real album makes
        # every one of those minutes matter. Bounded concurrency still
        # avoids the original problem this was written to prevent (every
        # photo hitting R2/CPU at once, all colliding with Chromium's own
        # page-load) — it's just a wider "one at a time" than literally 1
        # — and moved off the default pool onto the same dedicated one
        # regular photo processing already uses, so this doesn't compete
        # with AI curation's own default-pool work either.
        PDF_PREWARM_CONCURRENCY = 8
        album_doc = await db.albums.find_one({"id": album_id}, {"pages": 1})
        interior_pages = (album_doc or {}).get("pages", [])
        photo_ids = {
            it["photo_id"]
            for pg in interior_pages
            for it in (pg.get("items") or [])
            if it.get("type") == "photo" and it.get("photo_id")
        }
        if photo_ids:
            loop = asyncio.get_event_loop()
            prewarm_semaphore = asyncio.Semaphore(PDF_PREWARM_CONCURRENCY)

            async def _prewarm_one(photo):
                if photo.get("print_path") and photo.get("print_size"):
                    return  # already cached from an earlier order/preview, size already on record
                async with prewarm_semaphore:
                    print_path, print_bytes = await loop.run_in_executor(photo_processing_executor, generate_print_variant, photo)
                if print_path:
                    await db.photos.update_one({"id": photo["id"]}, {"$set": {"print_path": print_path, "print_size": len(print_bytes)}})

            photos_cursor = db.photos.find({"id": {"$in": list(photo_ids)}}, {"_id": 0})
            photos_list = await photos_cursor.to_list(len(photo_ids))
            await asyncio.gather(*(_prewarm_one(photo) for photo in photos_list))

        token = create_token(user_id)
        loop = asyncio.get_event_loop()

        # A large album's print-quality PDF can be big enough (many
        # hundreds of full-resolution photos) that transferring it out of
        # the headless browser hits a hard ~512MB string-length ceiling
        # the JS engine itself enforces on any single value —
        # "Page.pdf: Cannot create a string longer than 0x1fffffe8
        # characters" — a wall no amount of server memory gets past,
        # because it isn't a memory limit at all.
        #
        # Predicting the right chunk size from the source photos' own file
        # weight isn't reliable on its own — nothing confirms how large
        # Chromium's actual PDF encoding of a given set of images comes
        # out to. So this uses both: the print-variant byte weight already
        # on each photo's own record picks a *starting* chunk size close
        # to right, and a recursive split-and-retry remains as the safety
        # net for whatever the estimate still gets wrong.
        #
        # With every page capped at 4 photos (a real product constraint,
        # not an assumption) and this app's own observed print-variant
        # weights (0.5-3.6MB/photo, ~1.5MB average), a 200MB target chunk
        # holds roughly 20-30 pages on average — a meaningful drop from
        # the 80MB first tried here, which forced a 300-page album into
        # ~20+ separate chunks. Now that chunks are merged incrementally
        # as they finish (see below) rather than all held in memory until
        # the end, memory pressure is no longer the reason to keep chunks
        # small — chunk *count* is now the main cost (each one is a fresh
        # network round-trip through the print page), so the target
        # should be as large as the render ceiling comfortably allows.
        FALLBACK_PHOTO_BYTES_ESTIMATE = 2 * 1024 * 1024
        photo_sizes = {}
        if photo_ids:
            size_cursor = db.photos.find({"id": {"$in": list(photo_ids)}}, {"_id": 0, "id": 1, "print_size": 1, "size": 1})
            async for p in size_cursor:
                photo_sizes[p["id"]] = p.get("print_size") or p.get("size") or FALLBACK_PHOTO_BYTES_ESTIMATE

        TARGET_INITIAL_CHUNK_BYTES = 200 * 1024 * 1024

        def _page_bytes(pg):
            return sum(
                photo_sizes.get(it.get("photo_id"), 0)
                for it in (pg.get("items") or [])
                if it.get("type") == "photo" and it.get("photo_id")
            )

        # Initial chunk boundaries from the byte estimate — computed here
        # (needs the async DB-backed photo_sizes above) but handed whole
        # to _render_all_chunks below, which does the actual rendering
        # entirely synchronously so every chunk (and every recursive
        # split-retry) can share the one browser it launches once, instead
        # of each chunk paying its own ~1-2s Chromium launch cost — on a
        # 20+-chunk album that overhead alone was tens of seconds.
        initial_ranges = []
        interior_count = len(interior_pages)
        if interior_count:
            chunk_start = 0
            chunk_bytes_so_far = 0
            for i, pg in enumerate(interior_pages):
                pg_bytes = _page_bytes(pg)
                if chunk_bytes_so_far > 0 and chunk_bytes_so_far + pg_bytes > TARGET_INITIAL_CHUNK_BYTES:
                    initial_ranges.append((chunk_start, i - 1))
                    chunk_start = i
                    chunk_bytes_so_far = 0
                chunk_bytes_so_far += pg_bytes
            initial_ranges.append((chunk_start, interior_count - 1))

        def _render_all_chunks(ranges: List[tuple]) -> bytes:
            """A fresh browser per chunk (and per recursive split-retry) —
            reusing one browser/page across many chunks was tried first to
            save Chromium's ~1-2s launch cost per chunk, but on a real
            large-album test it caused every subsequent navigation to get
            progressively slower (each chunk's images taking 40-50s+ to
            load instead of under a second, eventually timing out the
            30s networkidle wait outright) — almost certainly leftover
            memory/state inside Chromium's own render process building up
            across repeated heavy navigations in one page, never fully
            reclaimed between them. A fresh browser per chunk costs a
            couple of extra seconds each, in exchange for every chunk
            starting from a clean, known-good state — reliability over
            speed, by design."""

            def render_recursive(start: int, end: int, depth: int = 0) -> bytes:
                chunk_url = f"{FRONTEND_URL}/print/{album_id}?auth={token}&from={start}&to={end}"
                t0 = _time.monotonic()
                try:
                    chunk_bytes = render_pdf_via_browser_sync(chunk_url, log_label=f"Commande {order_id} : pages {start}-{end} (profondeur {depth})")
                    elapsed = _time.monotonic() - t0
                    logger.info(f"Commande {order_id} : pages {start}-{end} (profondeur {depth}) → {len(chunk_bytes)/1024/1024:.0f} Mio en {elapsed:.1f}s")
                    return chunk_bytes
                except Exception as e:
                    elapsed = _time.monotonic() - t0
                    if start == end:
                        logger.error(f"Commande {order_id} : la page {start} seule dépasse la limite après {elapsed:.1f}s, impossible de la découper davantage : {e}")
                        raise
                    mid = (start + end) // 2
                    logger.info(f"Commande {order_id} : pages {start}-{end} ont échoué après {elapsed:.1f}s ({e}) — nouveau découpage en {start}-{mid} et {mid+1}-{end}")
                    first_half = render_recursive(start, mid, depth + 1)
                    second_half = render_recursive(mid + 1, end, depth + 1)
                    writer2 = PdfWriter()
                    for half in (first_half, second_half):
                        r = PdfReader(BytesIO(half))
                        for pg2 in r.pages:
                            writer2.add_page(pg2)
                    out2 = BytesIO()
                    writer2.write(out2)
                    return out2.getvalue()

            if not ranges:
                return render_pdf_via_browser_sync(f"{FRONTEND_URL}/print/{album_id}?auth={token}")

            writer = PdfWriter()
            for start, end in ranges:
                chunk_bytes = render_recursive(start, end, 0)
                reader = PdfReader(BytesIO(chunk_bytes))
                for pg2 in reader.pages:
                    writer.add_page(pg2)
                del chunk_bytes, reader
                gc.collect()
            out = BytesIO()
            writer.write(out)
            return out.getvalue()

        if len(initial_ranges) > 1:
            logger.info(f"Commande {order_id} : point de départ estimé — {len(initial_ranges)} morceaux ({initial_ranges})")
        pdf_bytes = await loop.run_in_executor(pdf_render_executor, _render_all_chunks, initial_ranges)

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
        ids = [p["id"] for p in unused]
        if ids:
            await db.photos.update_many({"id": {"$in": ids}}, {"$set": {"is_deleted": True}})
    except Exception as e:
        logger.error(f"Échec du nettoyage des photos non sélectionnées pour l'album {album_id}: {e}")
