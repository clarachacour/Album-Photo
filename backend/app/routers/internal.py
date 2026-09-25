"""Maintenance endpoints called by Cloud Scheduler."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException

from app.config import (
    ALBUM_EXPIRING_WARNING_DAYS_BEFORE,
    CLEANUP_SECRET,
    DRAFT_ALBUM_RETENTION_DAYS,
    PDF_TASK_MAX_ATTEMPTS,
    UNFINISHED_ALBUM_REMINDER_DAYS,
)
from app.db import db
from app.services.orders import generate_order_pdf, purge_stale_pdf_generation_slots
from app.services.email import (
    send_album_expiring_soon_email,
    send_unfinished_album_reminder_email,
)
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


# ---------- Maintenance ----------
@router.post("/internal/remind-unfinished-albums")
async def remind_unfinished_albums(x_cleanup_secret: str = Header(None)):
    """Two-stage nudge for albums someone started and never finished,
    meant to run daily on the same Cloud Scheduler job pattern as
    /internal/cleanup-expired-albums (same secret, same "not reachable by
    end users" shape) — ideally scheduled to run just before it, so a
    freshly-sent final warning and the purge that makes it true stay a
    predictable few days apart rather than landing the same day.

    Stage 1 (reminder_stage 0 -> 1): album untouched for
    UNFINISHED_ALBUM_REMINDER_DAYS, never reminded — a gentle "come finish
    this" nudge.
    Stage 2 (reminder_stage 1 -> 2): album now within
    ALBUM_EXPIRING_WARNING_DAYS_BEFORE days of the purge cutoff, already
    got stage 1 but not stage 2 yet — a stronger "this is about to be
    deleted" warning. An album already at stage 1 is skipped for stage 2
    until it's actually that close, so nobody gets both emails on the same
    day.
    Ordered albums are never touched here, matching the purge job.
    """
    if not CLEANUP_SECRET:
        raise HTTPException(status_code=500, detail="CLEANUP_SECRET is not configured on this server")
    if x_cleanup_secret != CLEANUP_SECRET:
        raise HTTPException(status_code=401, detail="Not authorized")

    now = datetime.now(timezone.utc)
    ordered_album_ids = set(await db.orders.distinct("album_id"))

    stage1_cutoff = (now - timedelta(days=UNFINISHED_ALBUM_REMINDER_DAYS)).isoformat()
    stage1_candidates = await db.albums.find(
        # updated_at, not created_at — someone actively working on an album
        # created a while ago but touched yesterday shouldn't get a "finish
        # this" nudge; the purge cutoff (stage 2) is deliberately different,
        # since that one has to match the purge job's own created_at basis
        # exactly for "days_left" to be accurate.
        {"is_deleted": {"$ne": True}, "updated_at": {"$lt": stage1_cutoff}, "reminder_stage": {"$exists": False}},
        {"_id": 0},
    ).to_list(2000)

    stage2_cutoff = (now - timedelta(days=DRAFT_ALBUM_RETENTION_DAYS - ALBUM_EXPIRING_WARNING_DAYS_BEFORE)).isoformat()
    stage2_candidates = await db.albums.find(
        {"is_deleted": {"$ne": True}, "created_at": {"$lt": stage2_cutoff}, "reminder_stage": 1},
        {"_id": 0},
    ).to_list(2000)

    stage1_sent = 0
    for album in stage1_candidates:
        if album["id"] in ordered_album_ids:
            continue
        user = await db.users.find_one({"id": album["user_id"]}, {"_id": 0})
        if user and user.get("email"):
            send_unfinished_album_reminder_email(user["email"], user.get("name"), album)
        await db.albums.update_one({"id": album["id"]}, {"$set": {"reminder_stage": 1}})
        stage1_sent += 1

    stage2_sent = 0
    for album in stage2_candidates:
        if album["id"] in ordered_album_ids:
            continue
        purge_at = datetime.fromisoformat(album["created_at"]) + timedelta(days=DRAFT_ALBUM_RETENTION_DAYS)
        days_left = max(1, (purge_at - now).days)
        user = await db.users.find_one({"id": album["user_id"]}, {"_id": 0})
        if user and user.get("email"):
            send_album_expiring_soon_email(user["email"], user.get("name"), album, days_left)
        await db.albums.update_one({"id": album["id"]}, {"$set": {"reminder_stage": 2}})
        stage2_sent += 1

    return {"stage1_sent": stage1_sent, "stage2_sent": stage2_sent}

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
