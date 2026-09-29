"""Deleting an account (the customer's "Delete my account" button)."""
import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import APP_NAME
from app.core.executors import run_blocking
from app.db import db
from app.services.storage import delete_object, delete_prefix

logger = logging.getLogger(__name__)

# An order in any other status is still being made or shipped: the account
# can't be deleted until it's done (we still need its address, and the
# customer their order page).
FINISHED_ORDER_STATUSES = ("delivered", "cancelled")


async def delete_account(user: dict) -> dict:
    """Deletes the account and everything in it: albums, photos and every
    file uploaded (the whole users/<id>/ folder in storage), order PDFs
    (they contain the photos), mobile upload links and contact messages.

    Past orders are kept — they are sales records the business must keep
    for its accounts — but no longer point to any photo or file."""
    user_id = user["id"]
    orders = await db.orders.find({"user_id": user_id}, {"_id": 0}).to_list(1000)
    if any(o.get("status") not in FINISHED_ORDER_STATUSES for o in orders):
        raise HTTPException(
            status_code=409,
            detail="An order is still in progress: the account can be deleted once it has been delivered. Contact us if you need help.",
        )

    files = await run_blocking(delete_prefix, f"{APP_NAME}/users/{user_id}/")
    for order in orders:
        delete_object(order.get("pdf_path"))
    now = datetime.now(timezone.utc).isoformat()
    await db.orders.update_many(
        {"user_id": user_id},
        {"$set": {"pdf_path": None, "pdf_ready": False, "account_deleted_at": now}},
    )
    albums = await db.albums.delete_many({"user_id": user_id})
    photos = await db.photos.delete_many({"user_id": user_id})
    await db.mobile_sessions.delete_many({"user_id": user_id})
    await db.contact_messages.delete_many({"email": user.get("email")})
    await db.users.delete_one({"id": user_id})
    logger.info(f"Compte {user_id} supprimé : {albums.deleted_count} album(s), {photos.deleted_count} photo(s), {files} fichier(s)")
    return {"albums": albums.deleted_count, "photos": photos.deleted_count, "files": files}
