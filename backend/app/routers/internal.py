"""Maintenance endpoints called by Cloud Scheduler."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException

from app.config import (
    CLEANUP_SECRET,
    DRAFT_ALBUM_RETENTION_DAYS,
    PDF_TASK_MAX_ATTEMPTS,
)
from app.db import db
from app.services.processing import resume_layout
from app.services.orders import generate_order_pdf, purge_stale_pdf_generation_slots
from app.services.backup import backup_database
from app.services.delivery import sync_all_deliveries
from app.services.print_groups import flush_printer_queue
from app.services.reminders import send_reminders
from app.services.storage import delete_object

router = APIRouter()


# ---------- Order PDF (called by the Cloud Tasks queue) ----------
@router.post("/internal/orders/{order_id}/generate-pdf")
async def internal_generate_order_pdf(
    order_id: str,
    x_cleanup_secret: str = Header(None),
    x_cloudtasks_taskretrycount: str = Header(None),
):
    """Generates an order's PDF; called by the PDF_TASKS_QUEUE queue (see
    app/services/tasks.py). An error response makes the queue try again
    later; the admin is emailed after the last attempt."""
    if not CLEANUP_SECRET:
        raise HTTPException(status_code=500, detail="CLEANUP_SECRET is not configured on this server")
    if x_cleanup_secret != CLEANUP_SECRET:
        raise HTTPException(status_code=401, detail="Not authorized")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        return {"skipped": "order not found"}
    if order.get("pdf_ready"):
        return {"skipped": "PDF already ready"}
    await purge_stale_pdf_generation_slots()
    if await db.pdf_generation_slots.find_one({"order_id": order_id}):
        # A previous attempt is still rendering: try again later.
        raise HTTPException(status_code=409, detail="A generation is already in progress for this order")
    attempt = int(x_cloudtasks_taskretrycount or 0) + 1
    final_attempt = attempt >= PDF_TASK_MAX_ATTEMPTS
    ok = await generate_order_pdf(order_id, order["album_id"], order["user_id"], final_attempt=final_attempt)
    if not ok and not final_attempt:
        raise HTTPException(status_code=500, detail=f"PDF generation failed (attempt {attempt}), the queue will retry")
    return {"pdf_ready": ok, "attempt": attempt}


# ---------- Album layout (called by the Cloud Tasks queue) ----------
@router.post("/internal/albums/{album_id}/layout")
async def internal_album_layout(album_id: str, x_cleanup_secret: str = Header(None)):
    """Lays out the album (see start_full_layout and rescue_layout). A
    layout that fails leaves the album in "error" for the person to retry:
    no point in the queue trying the same photos again."""
    if not CLEANUP_SECRET:
        raise HTTPException(status_code=500, detail="CLEANUP_SECRET is not configured on this server")
    if x_cleanup_secret != CLEANUP_SECRET:
        raise HTTPException(status_code=401, detail="Not authorized")
    album = await db.albums.find_one({"id": album_id}, {"_id": 0, "user_id": 1})
    if not album:
        return {"skipped": "album not found"}
    await resume_layout(album_id, album["user_id"])
    fresh = await db.albums.find_one({"id": album_id}, {"_id": 0, "status": 1})
    return {"status": (fresh or {}).get("status")}


# ---------- Maintenance ----------
@router.post("/internal/remind-unfinished-albums")
async def remind_unfinished_albums(x_cleanup_secret: str = Header(None)):
    """Every reminder email due (see services/reminders.py). The same runs
    every 30 minutes with /internal/sync-deliveries; this one stays for a
    daily job, if there is one."""
    if not CLEANUP_SECRET:
        raise HTTPException(status_code=500, detail="CLEANUP_SECRET is not configured on this server")
    if x_cleanup_secret != CLEANUP_SECRET:
        raise HTTPException(status_code=401, detail="Not authorized")
    return await send_reminders()

@router.post("/internal/cleanup-expired-albums")
async def cleanup_expired_albums(x_cleanup_secret: str = Header(None)):
    """Deletes albums that were never ordered and are older than
    DRAFT_ALBUM_RETENTION_DAYS (default 30) — their photos on R2, cover
    image, and the album document itself. An ordered album is never touched
    here regardless of age (see _delete_unselected_photos for what happens
    to its unselected photos, at order time instead).

    Not reachable by end users — meant to be called on a schedule by Cloud
    Scheduler, authenticated with CLEANUP_SECRET rather than a user token,
    since there's no logged-in user in that context.
    """
    if not CLEANUP_SECRET:
        raise HTTPException(status_code=500, detail="CLEANUP_SECRET is not configured on this server")
    if x_cleanup_secret != CLEANUP_SECRET:
        raise HTTPException(status_code=401, detail="Not authorized")

    cutoff = (datetime.now(timezone.utc) - timedelta(days=DRAFT_ALBUM_RETENTION_DAYS)).isoformat()
    ordered_album_ids = set(await db.orders.distinct("album_id"))

    candidates = await db.albums.find(
        {"is_deleted": {"$ne": True}, "created_at": {"$lt": cutoff}}, {"_id": 0}
    ).to_list(2000)

    deleted_count = 0
    for album in candidates:
        if album["id"] in ordered_album_ids:
            continue  # ever ordered, however long ago — never auto-purged
        photos = await db.photos.find({"album_id": album["id"]}, {"_id": 0}).to_list(5000)
        for p in photos:
            delete_object(p.get("storage_path"))
            delete_object(p.get("thumbnail_path"))
            delete_object(p.get("medium_path"))
            delete_object(p.get("print_path"))
            delete_object(p.get("print_full_path"))
        delete_object(album.get("cover_image_path"))
        await db.photos.update_many({"album_id": album["id"]}, {"$set": {"is_deleted": True}})
        await db.albums.update_one({"id": album["id"]}, {"$set": {"is_deleted": True}})
        deleted_count += 1

    return {"checked": len(candidates), "deleted": deleted_count, "retention_days": DRAFT_ALBUM_RETENTION_DAYS}


# ---------- Daily database backup (Cloud Scheduler) ----------
@router.post("/internal/backup")
async def internal_backup(x_cleanup_secret: str = Header(None)):
    """Copies the whole database to R2 (see app/services/backup.py). Meant
    to be called once a day by Cloud Scheduler, like the cleanup above."""
    if not CLEANUP_SECRET:
        raise HTTPException(status_code=500, detail="CLEANUP_SECRET is not configured on this server")
    if x_cleanup_secret != CLEANUP_SECRET:
        raise HTTPException(status_code=401, detail="Not authorized")
    return await backup_database()


# ---------- Wakilni deliveries (Cloud Scheduler, e.g. every 30 minutes) ----------
@router.post("/internal/sync-deliveries")
async def internal_sync_deliveries(x_cleanup_secret: str = Header(None)):
    """Sends the printer the albums whose grouping wait is over (see
    services/print_groups.py), then follows every Wakilni delivery still on
    its way (see services/delivery.py): shipped and delivered emails,
    alerts to the admin."""
    if not CLEANUP_SECRET:
        raise HTTPException(status_code=500, detail="CLEANUP_SECRET is not configured on this server")
    if x_cleanup_secret != CLEANUP_SECRET:
        raise HTTPException(status_code=401, detail="Not authorized")
    # The printer's emails waiting to group a customer's albums go first.
    printer_emails = await flush_printer_queue()
    result = {**(await sync_all_deliveries()), "printer_emails": printer_emails}
    # The customers' reminders (cart, album not ordered), when due.
    return {**result, **(await send_reminders())}
