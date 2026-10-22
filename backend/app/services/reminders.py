"""Reminder emails to customers: a cart left with albums in it, an album
started but never ordered (and, before the purge, a warning that it will be
deleted). Run by the scheduled job every 30 minutes (/internal/sync-deliveries)
and by /internal/remind-unfinished-albums; each email goes out once, so
running them often costs nothing.

Sent during the day in Lebanon only, in the customer's language (the one
the album was created in), each with a link to stop them (the deletion
warning excepted: it's about their photos, not a nudge to buy).
"""
from datetime import datetime, timedelta, timezone

from app.config import (
    ALBUM_EXPIRING_WARNING_DAYS_BEFORE,
    BACKEND_URL,
    CART_REMINDER_HOURS,
    DRAFT_ALBUM_RETENTION_DAYS,
    UNFINISHED_ALBUM_REMINDER_DAYS,
)
from app.core.executors import run_email
from app.core.signed_links import sign_order_action, verify_order_action
from app.db import db
from app.services.email import (
    send_album_expiring_soon_email,
    send_cart_reminder_email,
    send_unfinished_album_reminder_email,
)

# Hours (UTC) when reminders may go out: about 9-10 am to 8-9 pm in Lebanon
# (UTC+2 in winter, UTC+3 in summer) — never in the middle of the night.
SENDING_HOURS_UTC = range(7, 18)


def stop_url(user_id: str) -> str:
    """The link, in each reminder, that stops them for this account."""
    return f"{BACKEND_URL}/api/reminders/stop?user={user_id}&token={sign_order_action(user_id, 'stop-reminders')}"


def verify_stop(user_id: str, token: str) -> bool:
    return verify_order_action(user_id, "stop-reminders", token)


async def _customer(user_id: str):
    """The account to remind, or None (no email, or reminders stopped)."""
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "email": 1, "name": 1, "reminders_off": 1})
    if not user or not user.get("email") or user.get("reminders_off"):
        return None
    return user


async def remind_carts(now: datetime) -> int:
    """One email for a cart left untouched CART_REMINDER_HOURS, listing what's
    in it; again only if the cart changes afterwards."""
    cutoff = (now - timedelta(hours=CART_REMINDER_HOURS)).isoformat()
    carts = await db.carts.find({"items.0": {"$exists": True}, "updated_at": {"$lt": cutoff}}, {"_id": 0}).to_list(2000)
    sent = 0
    for cart in carts:
        if cart.get("reminded_at") and cart["reminded_at"] >= cart["updated_at"]:
            continue  # already reminded about this cart as it is
        await db.carts.update_one({"user_id": cart["user_id"]}, {"$set": {"reminded_at": now.isoformat()}})
        user = await _customer(cart["user_id"])
        if not user:
            continue
        lines, lang = [], None
        for item in cart["items"]:
            if item.get("kind") == "gift":
                lines.append((f"{item.get('size')} · {item.get('page_tier')} pages", "gift"))
                lang = lang or item.get("lang")
                continue
            album = await db.albums.find_one({"id": item.get("album_id"), "is_deleted": {"$ne": True}}, {"_id": 0, "title": 1, "lang": 1})
            if album:
                lines.append((album.get("title") or "Album", item.get("kind")))
                lang = lang or album.get("lang")
        if lines:
            await run_email(send_cart_reminder_email, user["email"], user.get("name"), lines, lang or "en", stop_url(cart["user_id"]))
            sent += 1
    return sent


async def remind_unfinished_albums(now: datetime) -> dict:
    """Two stages for albums started and never ordered:
    1. untouched for UNFINISHED_ALBUM_REMINDER_DAYS: "come finish it" (not
       for an album in the cart: the cart's reminder speaks of it);
    2. ALBUM_EXPIRING_WARNING_DAYS_BEFORE days before the purge
       (/internal/cleanup-expired-albums): it will be deleted.
    An ordered album is never touched, matching the purge."""
    ordered = set(await db.orders.distinct("album_id"))
    in_carts = set(await db.carts.distinct("items.album_id"))

    stage1_cutoff = (now - timedelta(days=UNFINISHED_ALBUM_REMINDER_DAYS)).isoformat()
    # updated_at, not created_at: an album worked on yesterday gets no nudge.
    # The deletion warning goes by created_at, as the purge does.
    stage1 = await db.albums.find(
        {"is_deleted": {"$ne": True}, "updated_at": {"$lt": stage1_cutoff}, "reminder_stage": {"$exists": False}}, {"_id": 0}
    ).to_list(2000)
    stage2_cutoff = (now - timedelta(days=DRAFT_ALBUM_RETENTION_DAYS - ALBUM_EXPIRING_WARNING_DAYS_BEFORE)).isoformat()
    stage2 = await db.albums.find(
        {"is_deleted": {"$ne": True}, "created_at": {"$lt": stage2_cutoff}, "reminder_stage": 1}, {"_id": 0}
    ).to_list(2000)

    stage1_sent = 0
    for album in stage1:
        if album["id"] in ordered:
            continue
        await db.albums.update_one({"id": album["id"]}, {"$set": {"reminder_stage": 1}})
        if album["id"] in in_carts:
            continue
        user = await _customer(album["user_id"])
        if user:
            await run_email(send_unfinished_album_reminder_email, user["email"], user.get("name"), album, stop_url(album["user_id"]))
            stage1_sent += 1

    stage2_sent = 0
    for album in stage2:
        if album["id"] in ordered:
            continue
        purge_at = datetime.fromisoformat(album["created_at"]) + timedelta(days=DRAFT_ALBUM_RETENTION_DAYS)
        days_left = max(1, (purge_at - now).days)
        await db.albums.update_one({"id": album["id"]}, {"$set": {"reminder_stage": 2}})
        user = await db.users.find_one({"id": album["user_id"]}, {"_id": 0, "email": 1, "name": 1})
        if user and user.get("email"):
            await run_email(send_album_expiring_soon_email, user["email"], user.get("name"), album, days_left)
            stage2_sent += 1

    return {"stage1_sent": stage1_sent, "stage2_sent": stage2_sent}


async def send_reminders(now: datetime = None) -> dict:
    """Every reminder due, during the day only."""
    now = now or datetime.now(timezone.utc)
    if now.hour not in SENDING_HOURS_UTC:
        return {"reminders": "outside sending hours"}
    return {"carts_reminded": await remind_carts(now), **(await remind_unfinished_albums(now))}
