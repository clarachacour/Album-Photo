"""Shared album rules used by several routers."""

from fastapi import HTTPException

from app.db import db


async def reject_if_ordered(album_id: str, album: dict | None = None):
    """An order is a customer's paid, fixed record of what they'll
    receive — nothing that changes what actually prints (text, fonts,
    positions, photos, cover) should be editable once an album has been
    ordered, or a customer could open their album later, move something,
    and have a *future* regeneration silently print something different
    from what they paid for (there's no per-order snapshot of album
    content — generate_order_pdf always renders whatever the live album
    currently looks like). Matches delete_album's existing rule, and the
    30-day draft purge's (see cleanup_expired_albums) — both already treat
    "has an order" as the same bright line.

    admin_unlocked is the deliberate escape hatch for the rare case a
    mistake needs fixing on an already-ordered album (e.g. text placed
    wrong on the cover) — nothing in the UI sets this; it's a flag set
    directly in MongoDB on one specific album (db.albums.updateOne({id:
    "..."}, {$set: {admin_unlocked: true}})) when that's genuinely
    intended, and should be unset the same way once the fix is made, to
    put the lock back."""
    if album is None:
        album = await db.albums.find_one({"id": album_id}, {"admin_unlocked": 1})
    if album and album.get("admin_unlocked"):
        return
    if await db.orders.find_one({"album_id": album_id}):
        raise HTTPException(status_code=403, detail="This album has already been ordered and can no longer be edited")
