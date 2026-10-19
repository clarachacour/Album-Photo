"""The customer's cart, kept on their account (it follows them from phone
to computer): albums added one by one — printed, as a PDF, or both — then
ordered all at once, in one checkout (see services/checkout.py)."""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pymongo.errors import DuplicateKeyError

from app.core.auth import get_current_user
from app.core.executors import run_email
from app.db import db
from app.routers.albums import _slim_stored_cover
from app.schemas import CartItemInput, CartQuantityInput, CheckoutInput
from app.services.checkout import build_order_doc, unit_price_cents
from app.services.email import send_checkout_confirmation_email, send_order_confirmation_email
from app.services.orders import start_order_pdf_generation
from app.services.pricing import SHIPPING_PRICE_CENTS, TERMS_VERSION, billed_page_count

router = APIRouter()
logger = logging.getLogger(__name__)

# What the cart shows of each album (not its pages: they can be heavy).
ALBUM_FIELDS = {"_id": 0, "id": 1, "title": 1, "size": 1, "orientation": 1, "target_pages": 1, "pages.id": 1,
                "cover": 1, "cover_template_id": 1, "cover_image_path": 1, "status": 1}


def _same_kind(kind: str):
    # Orders from before digital albums have no kind: they're printed ones.
    return {"$in": ["print", None]} if kind == "print" else "digital"


async def _items(user: dict) -> list:
    cart = await db.carts.find_one({"user_id": user["id"]}, {"_id": 0}) or {}
    return cart.get("items") or []


async def _save(user: dict, items: list):
    now = datetime.now(timezone.utc).isoformat()
    await db.carts.update_one({"user_id": user["id"]}, {"$set": {"items": items, "updated_at": now}}, upsert=True)


async def _problem(album: dict, kind: str):
    """Why this album can't be ordered in this version (None: it can)."""
    if not album.get("pages") or album.get("status") == "draft":
        return "no_pages"
    if await db.orders.find_one({"album_id": album["id"], "kind": _same_kind(kind)}, {"_id": 1}):
        return "already_ordered"
    return None


async def _view(user: dict) -> dict:
    """The cart as the site shows it: each line priced on the server, the
    delivery once for all the printed albums, the total."""
    lines, kept = [], []
    for item in await _items(user):
        album = await db.albums.find_one({"id": item["album_id"], "user_id": user["id"]}, ALBUM_FIELDS)
        if not album:
            continue  # the album was deleted: gone from the cart too
        kept.append(item)
        await _slim_stored_cover(album)
        unit = unit_price_cents(album, item["kind"])
        quantity = 1 if item["kind"] == "digital" else int(item.get("quantity") or 1)
        lines.append({
            **item,
            "quantity": quantity,
            "unit_price_cents": unit,
            "line_total_cents": unit * quantity,
            "page_count": billed_page_count(album),
            "problem": await _problem(album, item["kind"]),
            "album": {k: v for k, v in album.items() if k != "pages"},
        })
    if len(kept) != len(await _items(user)):
        await _save(user, kept)
    valid = [line for line in lines if not line["problem"]]
    shipping = SHIPPING_PRICE_CENTS if any(line["kind"] == "print" for line in valid) else 0
    subtotal = sum(line["line_total_cents"] for line in valid)
    return {"items": lines, "count": len(lines), "subtotal_cents": subtotal, "shipping_cents": shipping,
            "total_cents": subtotal + shipping, "currency": "usd"}


@router.get("/cart")
async def get_cart(user: dict = Depends(get_current_user)):
    return await _view(user)


@router.post("/cart/items")
async def add_to_cart(data: CartItemInput, user: dict = Depends(get_current_user)):
    """Adds an album (one version) to the cart — or, already there, sets
    its quantity."""
    album = await db.albums.find_one({"id": data.album_id, "user_id": user["id"]}, ALBUM_FIELDS)
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    problem = await _problem(album, data.kind)
    if problem == "no_pages":
        raise HTTPException(status_code=400, detail="This album has no pages yet")
    if problem == "already_ordered":
        raise HTTPException(status_code=409, detail="An order already exists for this album")
    items = await _items(user)
    quantity = 1 if data.kind == "digital" else data.quantity
    for item in items:
        if item["album_id"] == data.album_id and item["kind"] == data.kind:
            item["quantity"] = quantity
            break
    else:
        if len(items) >= 30:
            raise HTTPException(status_code=400, detail="Your cart is full")
        items.append({"id": str(uuid.uuid4()), "album_id": data.album_id, "kind": data.kind, "quantity": quantity,
                      "added_at": datetime.now(timezone.utc).isoformat()})
    await _save(user, items)
    return await _view(user)


@router.patch("/cart/items/{item_id}")
async def set_cart_quantity(item_id: str, data: CartQuantityInput, user: dict = Depends(get_current_user)):
    items = await _items(user)
    item = next((i for i in items if i["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Not in your cart")
    item["quantity"] = 1 if item["kind"] == "digital" else data.quantity
    await _save(user, items)
    return await _view(user)


@router.delete("/cart/items/{item_id}")
async def remove_from_cart(item_id: str, user: dict = Depends(get_current_user)):
    await _save(user, [i for i in await _items(user) if i["id"] != item_id])
    return await _view(user)


@router.post("/cart/checkout")
async def checkout(data: CheckoutInput, user: dict = Depends(get_current_user)):
    """Orders everything in the cart at once: one order per album and
    version (so the PDF, printer, delivery and admin work as for a single
    one), grouped under one checkout. The delivery is paid once, on the
    first printed album; the printed albums go to the printer and the
    courier together (see services/print_groups.py)."""
    view = await _view(user)
    if not view["items"]:
        raise HTTPException(status_code=400, detail="Your cart is empty")
    if any(line["problem"] for line in view["items"]):
        raise HTTPException(status_code=409, detail="Something in your cart can't be ordered any more — please check it")
    has_print = any(line["kind"] == "print" for line in view["items"])
    if has_print and not data.shipping_address:
        raise HTTPException(status_code=400, detail="A delivery address is needed for a printed album")
    if data.accepted_terms_version != TERMS_VERSION:
        raise HTTPException(status_code=400, detail="Please accept the current terms of sale to place your order")
    checkout_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    address = data.shipping_address.dict() if data.shipping_address else None
    orders, shipping_paid = [], False
    # Printed albums first: the first one carries the delivery.
    for line in sorted(view["items"], key=lambda i: i["kind"] != "print"):
        album = await db.albums.find_one({"id": line["album_id"], "user_id": user["id"]}, {"_id": 0, "pages.id": 1, "id": 1,
                                          "title": 1, "size": 1, "orientation": 1, "target_pages": 1})
        shipping = 0
        if line["kind"] == "print" and not shipping_paid:
            shipping, shipping_paid = SHIPPING_PRICE_CENTS, True
        doc = await build_order_doc(user, album, line["kind"], line["quantity"], address, shipping, checkout_id, now)
        try:
            await db.orders.insert_one(doc)
        except DuplicateKeyError:
            # Ordered meanwhile (another tab): that one stands.
            if shipping:
                shipping_paid = False
            continue
        doc.pop("_id", None)
        orders.append(doc)
    if not orders:
        raise HTTPException(status_code=409, detail="An order already exists for these albums")
    ordered = {(o["album_id"], o["kind"]) for o in orders}
    await _save(user, [i for i in await _items(user) if (i["album_id"], i["kind"]) not in ordered])
    if len(orders) == 1:
        await run_email(send_order_confirmation_email, user.get("email"), user.get("name"), orders[0])
    else:
        await run_email(send_checkout_confirmation_email, user.get("email"), user.get("name"), orders)
    logger.info(f"Panier {checkout_id} : {len(orders)} commande(s) passée(s)")
    # Each album's PDF (through the Cloud Tasks queue when configured).
    for order in orders:
        await start_order_pdf_generation(order)
    fresh = await db.orders.find({"checkout_id": checkout_id}, {"_id": 0}).to_list(50)
    return {"checkout_id": checkout_id, "orders": fresh}
