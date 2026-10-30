"""ONE-TIME TOOL — deleting the test accounts and orders made before the
launch, from the admin. To be removed once the cleanup is done (this file,
its line in main.py, frontend/src/components/admin/TestCleanupPanel.jsx
and its line in AdminOrdersPage.jsx).

Everything goes through the same deletions as the site's own buttons, so
the photos and PDFs in storage go too (not only the database records)."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import ADMIN_EMAIL
from app.core.auth import get_current_user, require_admin
from app.core.order_number import order_number
from app.db import db
from app.services.accounts import delete_account
from app.services.storage import delete_object

router = APIRouter()
logger = logging.getLogger(__name__)


class Confirm(BaseModel):
    # The account's email (or the order's number), typed again.
    confirm: str = Field(min_length=1, max_length=200)


async def _delete_album(album_id: str):
    """The album and its photos, files included (as DELETE /albums/{id})."""
    album = await db.albums.find_one({"id": album_id})
    if not album:
        return
    for p in await db.photos.find({"album_id": album_id}, {"_id": 0}).to_list(5000):
        for key in ("storage_path", "thumbnail_path", "medium_path", "print_path", "print_full_path"):
            delete_object(p.get(key))
    delete_object(album.get("cover_image_path"))
    await db.albums.delete_one({"id": album_id})
    await db.photos.delete_many({"album_id": album_id})


async def _delete_order(order: dict):
    delete_object(order.get("pdf_path"))
    await db.pdf_generation_slots.delete_many({"order_id": order["id"]})
    await db.orders.delete_one({"id": order["id"]})


@router.get("/admin/test-cleanup/accounts")
async def list_accounts(user: dict = Depends(get_current_user)):
    require_admin(user)
    users = await db.users.find({}, {"_id": 0, "id": 1, "email": 1, "name": 1, "created_at": 1}).sort("created_at", -1).to_list(5000)
    out = []
    for u in users:
        out.append({
            **u,
            "albums": await db.albums.count_documents({"user_id": u["id"]}),
            "orders": await db.orders.count_documents({"user_id": u["id"]}),
            "is_admin": bool(ADMIN_EMAIL) and u.get("email") == ADMIN_EMAIL,
        })
    return out


@router.post("/admin/test-cleanup/accounts/{user_id}/delete")
async def delete_test_account(user_id: str, data: Confirm, user: dict = Depends(get_current_user)):
    """The account, its albums, photos, orders (with their PDFs), cart,
    credit and gift cards bought — for good. No email is sent."""
    require_admin(user)
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="No such account")
    if target.get("email") == ADMIN_EMAIL or target["id"] == user["id"]:
        raise HTTPException(status_code=400, detail="This is the admin account: it can't be deleted here")
    if data.confirm.strip().lower() != (target.get("email") or "").lower():
        raise HTTPException(status_code=400, detail="Type the account's email exactly to confirm")
    orders = await db.orders.find({"user_id": user_id}, {"_id": 0}).to_list(1000)
    # Test orders: cancelled first (delete_account refuses an order in progress).
    await db.orders.update_many({"user_id": user_id}, {"$set": {"status": "cancelled"}})
    result = await delete_account(target)
    for o in orders:
        await _delete_order(o)
    await db.carts.delete_many({"user_id": user_id})
    await db.credits.delete_many({"user_id": user_id})
    await db.gift_cards.delete_many({"buyer_user_id": user_id})
    logger.info(f"Nettoyage des tests : compte {target.get('email')} supprimé avec {len(orders)} commande(s)")
    return {**result, "orders": len(orders)}


@router.get("/admin/test-cleanup/orders")
async def list_cancelled_orders(user: dict = Depends(get_current_user)):
    require_admin(user)
    orders = await db.orders.find({"status": "cancelled"}, {"_id": 0, "id": 1, "album_title": 1, "user_id": 1, "created_at": 1,
                                                            "shipping_address.full_name": 1}).sort("created_at", -1).to_list(2000)
    return [{**o, "number": order_number(o)} for o in orders]


@router.post("/admin/test-cleanup/orders/{order_id}/delete")
async def delete_test_order(order_id: str, data: Confirm, user: dict = Depends(get_current_user)):
    """A cancelled order for good, with its PDF — and its album and photos
    when no other order uses that album."""
    require_admin(user)
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="No such order")
    if order.get("status") != "cancelled":
        raise HTTPException(status_code=400, detail="Cancel the order first (only cancelled orders can be deleted)")
    if data.confirm.strip().upper() != order_number(order):
        raise HTTPException(status_code=400, detail="Type the order number exactly to confirm")
    await _delete_order(order)
    if order.get("album_id") and not await db.orders.find_one({"album_id": order["album_id"]}):
        await _delete_album(order["album_id"])
    logger.info(f"Nettoyage des tests : commande {order_number(order)} supprimée")
    return {"deleted": True}
