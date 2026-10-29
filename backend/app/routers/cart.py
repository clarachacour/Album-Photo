"""The customer's cart, kept on their account (it follows them from phone
to computer): albums added one by one — printed, as a PDF, or both — then
ordered all at once, in one checkout (see services/checkout.py)."""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pymongo.errors import DuplicateKeyError

from app.core.auth import get_current_user
from app.core.executors import run_email
from app.db import db
from app.routers.albums import _slim_stored_cover
from app.schemas import CartItemInput, CartQuantityInput, CheckoutInput, GiftCardInput, PromoApplyInput
from app.services.checkout import build_order_doc, unit_price_cents
from app.config import FRONTEND_URL
from app.services import gift_cards, promo_codes, reminders
from app.services.email import send_checkout_confirmation_email, send_gift_cards_email, send_order_confirmation_email
from app.services import payments
from app.services.payments import NEEDS_ONLINE_PAYMENT, collect_payment
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
    if kind == "digital" and not payments.ONLINE_PAYMENT:
        return "payment_soon"
    if not album.get("pages") or album.get("status") == "draft":
        return "no_pages"
    if await db.orders.find_one({"album_id": album["id"], "kind": _same_kind(kind)}, {"_id": 1}):
        return "already_ordered"
    return None


def _gift_line(item: dict) -> dict:
    value = gift_cards.gift_value_cents(item["size"], int(item["page_tier"]))
    return {**item, "quantity": 1, "unit_price_cents": value, "line_total_cents": value,
            "problem": None if payments.ONLINE_PAYMENT else "payment_soon"}


def _due(line: dict) -> int:
    return line["line_total_cents"] - line.get("discount_cents", 0)


def plan_credit(lines: list, shipping: int, balance: int) -> dict:
    """How the customer's credit (gift cards) is used on the albums, after
    any promo code: the printed ones and their delivery first (less for
    the courier to collect), then the PDFs. Not on gift cards bought."""
    prints = sum(_due(line) for line in lines if line["kind"] == "print") + shipping
    digitals = sum(_due(line) for line in lines if line["kind"] == "digital")
    on_prints = min(balance, prints)
    on_digitals = min(balance - on_prints, digitals)
    return {"applied": on_prints + on_digitals, "cash": prints - on_prints}


async def _promo(user: dict):
    """The promo code entered in the cart: ({"code", "percent", "problem"},
    the percent to take off — 0 when it can't be used), or (None, 0)."""
    cart = await db.carts.find_one({"user_id": user["id"]}, {"_id": 0, "promo_code": 1}) or {}
    if not cart.get("promo_code"):
        return None, 0
    promo, problem = await promo_codes.check(cart["promo_code"], user["id"])
    percent = promo["percent"] if promo and not problem else 0
    return {"code": cart["promo_code"], "percent": promo["percent"] if promo else None, "problem": problem}, percent


async def _view(user: dict) -> dict:
    """The cart as the site shows it: each line priced on the server, the
    delivery once for all the printed albums, the promo code and the
    credit taken off, the total."""
    lines, kept = [], []
    for item in await _items(user):
        if item["kind"] == "gift":
            kept.append(item)
            lines.append(_gift_line(item))
            continue
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
    # A promo code: a percentage off each album (not the delivery, not gift cards).
    promo, percent = await _promo(user)
    for line in valid:
        if line["kind"] != "gift":
            line["discount_cents"] = promo_codes.discount_cents(line["line_total_cents"], percent)
    discount = sum(line.get("discount_cents", 0) for line in valid)
    balance = await gift_cards.credit_balance(user["id"])
    # A promo code and gift card credit don't add up: with a code, the
    # credit isn't used (it stays on the account for a next order).
    credit = plan_credit(valid, shipping, 0 if percent else balance)
    gifts = sum(line["line_total_cents"] for line in valid if line["kind"] == "gift")
    return {"items": lines, "count": len(lines), "subtotal_cents": subtotal, "shipping_cents": shipping,
            "promo": promo, "discount_cents": discount,
            "credit_balance_cents": balance, "credit_applied_cents": credit["applied"],
            "total_cents": subtotal + shipping - discount - credit["applied"],
            # What's paid through the payment step (gift cards), and what the
            # courier collects in cash (the printed albums).
            "pay_now_cents": gifts, "cash_cents": credit["cash"], "currency": "usd"}


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
    if problem == "payment_soon":
        raise HTTPException(status_code=400, detail=NEEDS_ONLINE_PAYMENT)
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


@router.post("/cart/gifts")
async def add_gift_to_cart(data: GiftCardInput, user: dict = Depends(get_current_user)):
    """A gift card: an album (format, page count) offered to someone, with
    the words written on the card."""
    if not payments.ONLINE_PAYMENT:
        raise HTTPException(status_code=400, detail=NEEDS_ONLINE_PAYMENT)
    if not gift_cards.valid_choice(data.size, data.page_tier):
        raise HTTPException(status_code=400, detail="Please choose a format and a page count")
    items = await _items(user)
    if len(items) >= 30:
        raise HTTPException(status_code=400, detail="Your cart is full")
    items.append({"id": str(uuid.uuid4()), "kind": "gift", "album_id": None, "quantity": 1,
                  "size": data.size, "page_tier": data.page_tier, "recipient_name": data.recipient_name.strip(),
                  "message": data.message.strip(), "from_name": data.from_name.strip(), "lang": data.lang,
                  "added_at": datetime.now(timezone.utc).isoformat()})
    await _save(user, items)
    return await _view(user)


@router.patch("/cart/items/{item_id}")
async def set_cart_quantity(item_id: str, data: CartQuantityInput, user: dict = Depends(get_current_user)):
    items = await _items(user)
    item = next((i for i in items if i["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Not in your cart")
    item["quantity"] = 1 if item["kind"] in ("digital", "gift") else data.quantity
    await _save(user, items)
    return await _view(user)


@router.delete("/cart/items/{item_id}")
async def remove_from_cart(item_id: str, user: dict = Depends(get_current_user)):
    await _save(user, [i for i in await _items(user) if i["id"] != item_id])
    return await _view(user)


@router.post("/cart/promo")
async def apply_promo_code(data: PromoApplyInput, user: dict = Depends(get_current_user)):
    """The promo code typed in the cart: kept on the cart when this customer
    can use it; otherwise 400 with why ("promo_unknown", "promo_expired"…)."""
    promo, problem = await promo_codes.check(data.code, user["id"])
    if problem:
        raise HTTPException(status_code=400, detail=f"promo_{problem}")
    await db.carts.update_one({"user_id": user["id"]}, {"$set": {"promo_code": promo["code"]}}, upsert=True)
    return await _view(user)


@router.delete("/cart/promo")
async def remove_promo_code(user: dict = Depends(get_current_user)):
    await db.carts.update_one({"user_id": user["id"]}, {"$unset": {"promo_code": ""}})
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
    # A code that stopped working meanwhile (last day passed, switched off,
    # used in another tab): the customer sees why and removes it.
    if view["promo"] and view["promo"]["problem"]:
        raise HTTPException(status_code=409, detail="Your promo code can't be used any more — please remove it")
    promo = view["promo"]
    checkout_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    gift_lines = [line for line in view["items"] if line["kind"] == "gift"]
    album_lines = [line for line in view["items"] if line["kind"] != "gift"]
    # The payment step (gift cards for now; see services/payments.py).
    payment = None
    if gift_lines:
        payment = await collect_payment(user, checkout_id, view["pay_now_cents"], f"{len(gift_lines)} gift card(s)")
        if payment["status"] != "paid":
            raise HTTPException(status_code=402, detail="The payment didn't go through — nothing was ordered")
    address = data.shipping_address.dict() if data.shipping_address else None
    orders, shipping_paid = [], False
    # Printed albums first: the first one carries the delivery.
    for line in sorted(album_lines, key=lambda i: i["kind"] != "print"):
        album = await db.albums.find_one({"id": line["album_id"], "user_id": user["id"]}, {"_id": 0, "pages.id": 1, "id": 1,
                                          "title": 1, "size": 1, "orientation": 1, "target_pages": 1})
        shipping = 0
        if line["kind"] == "print" and not shipping_paid:
            shipping, shipping_paid = SHIPPING_PRICE_CENTS, True
        doc = await build_order_doc(user, album, line["kind"], line["quantity"], address, shipping, checkout_id, now,
                                    promo_code=promo["code"] if promo else None, promo_percent=promo["percent"] if promo else 0)
        try:
            await db.orders.insert_one(doc)
        except DuplicateKeyError:
            # Ordered meanwhile (another tab): that one stands.
            if shipping:
                shipping_paid = False
            continue
        doc.pop("_id", None)
        orders.append(doc)
    if album_lines and not orders and not gift_lines:
        raise HTTPException(status_code=409, detail="An order already exists for these albums")
    if not promo:
        await _apply_credit(user, orders)
    cards = [await gift_cards.create_gift_card(user, line, checkout_id, payment) for line in gift_lines]
    ordered = {(o["album_id"], o["kind"]) for o in orders}
    gift_ids = {line["id"] for line in gift_lines}
    await _save(user, [i for i in await _items(user) if (i.get("album_id"), i["kind"]) not in ordered and i["id"] not in gift_ids])
    if promo and orders:
        await db.carts.update_one({"user_id": user["id"]}, {"$unset": {"promo_code": ""}})
    if orders:
        orders = await db.orders.find({"checkout_id": checkout_id}, {"_id": 0}).to_list(50)
        if len(orders) == 1:
            await run_email(send_order_confirmation_email, user.get("email"), user.get("name"), orders[0])
        else:
            await run_email(send_checkout_confirmation_email, user.get("email"), user.get("name"), orders)
    if cards:
        pdfs = [(f"Everbook gift card {c['code']}.pdf", gift_cards.render_gift_card_pdf(c), "application/pdf") for c in cards]
        await run_email(send_gift_cards_email, user.get("email"), user.get("name"), cards, pdfs)
    logger.info(f"Panier {checkout_id} : {len(orders)} commande(s), {len(cards)} carte(s) cadeau")
    # Each album's PDF (through the Cloud Tasks queue when configured).
    for order in orders:
        await start_order_pdf_generation(order)
    fresh = await db.orders.find({"checkout_id": checkout_id}, {"_id": 0}).to_list(50)
    return {"checkout_id": checkout_id, "orders": fresh, "gift_cards": cards}


async def _apply_credit(user: dict, orders: list):
    """Takes the customer's credit (gift cards) off the new orders: printed
    albums first (less for the courier to collect), then PDFs."""
    if not orders:
        return
    planned = sum(o["total_price_cents"] for o in orders)
    used = await gift_cards.use_credit(user["id"], min(planned, await gift_cards.credit_balance(user["id"])))
    for o in sorted(orders, key=lambda o: o["kind"] != "print"):
        if used <= 0:
            break
        take = min(used, o["total_price_cents"])
        used -= take
        await db.orders.update_one(
            {"id": o["id"]}, {"$set": {"gift_credit_cents": take, "total_price_cents": o["total_price_cents"] - take}}
        )


# ---------- Stopping the reminder emails (link in each one) ----------
@router.get("/reminders/stop", response_class=HTMLResponse)
async def stop_reminders(user: str = Query(...), token: str = Query(None)):
    """The link at the bottom of each reminder email: no more reminders
    for this account (no login needed, the link is signed)."""
    if not reminders.verify_stop(user, token):
        raise HTTPException(status_code=403, detail="Invalid link")
    await db.users.update_one({"id": user}, {"$set": {"reminders_off": True}})
    return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Everbook</title></head>
<body style="margin:0;background:#F9F8F6;color:#1A1A17;font-family:Helvetica,Arial,sans-serif;display:flex;min-height:100vh;align-items:center;justify-content:center;text-align:center;padding:24px;box-sizing:border-box">
<div><p style="font-family:Georgia,serif;font-size:28px;margin:0 0 16px">Everbook</p>
<p>You won't receive reminders anymore.<br>Vous ne recevrez plus de rappels.</p>
<p><a href="{FRONTEND_URL}" style="color:#E56B55">{FRONTEND_URL.replace("https://", "")}</a></p></div></body></html>""")
