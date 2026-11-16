"""Placing orders: one album on its own (POST /orders), or everything in
the customer's cart at once (POST /cart/checkout, see routers/cart.py) —
one order per album and version, grouped under one checkout."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.services.pricing import (
    TERMS_VERSION,
    billed_page_count,
    compute_digital_price_cents,
    compute_order_price_cents,
)
from app.services.promo_codes import discount_cents


def unit_price_cents(album: dict, kind: str) -> int:
    pages = billed_page_count(album)
    return (compute_digital_price_cents if kind == "digital" else compute_order_price_cents)(album.get("size", "A4"), pages)


async def build_order_doc(
    user: dict,
    album: dict,
    kind: str,
    quantity: int,
    shipping_address: Optional[dict],
    shipping: int,
    checkout_id: Optional[str] = None,
    now: Optional[str] = None,
    promo_code: Optional[str] = None,
    promo_percent: int = 0,
    paid_online: Optional[dict] = None,
) -> dict:
    """A new order, priced on the server. `shipping`: what this order pays
    for delivery (a cart's printed albums pay it once, on the first).
    `promo_percent`: a promo code's percentage off the album (not the
    delivery). `paid_online`: the online payment (Whish Pay) that paid for
    it — the order starts "paid", nothing for the courier to collect."""
    digital = kind == "digital"
    unit_price = unit_price_cents(album, kind)
    quantity = 1 if digital else quantity
    # No combined price: the PDF and the printed book of the same album are
    # each at their own price.
    credit = 0
    discount = discount_cents(unit_price * quantity, promo_percent) if promo_code else 0
    now = now or datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "album_id": album["id"],
        "album_title": album.get("title", "Album"),
        "size": album.get("size", "A4"),
        "orientation": album.get("orientation", "portrait"),
        "kind": kind,
        "quantity": quantity,
        "unit_price_cents": unit_price,
        "shipping_price_cents": shipping,
        "credit_cents": credit,
        "total_price_cents": unit_price * quantity + shipping - credit - discount,
        "terms_version": TERMS_VERSION,
        "terms_accepted_at": now,
        "currency": "usd",
        "shipping_address": shipping_address if not digital else None,
        # Paid online (Whish Pay): "paid" — a digital album is sent as soon
        # as its PDF is made, a printed one goes to the printer and the
        # courier collects nothing. Otherwise a printed one is paid in cash
        # to the courier; a digital one (only before online payment) was
        # handed over at once.
        "status": "paid" if (digital or paid_online) else "pending_payment",
        # No credit on a printed copy for a PDF nobody paid for.
        "handed_over_unpaid": digital and not paid_online,
        "status_history": [{"status": "paid" if (digital or paid_online) else "pending_payment", "at": now}],
        "pdf_ready": False,
        "pdf_path": None,
        "tracking_number": None,
        "created_at": now,
        "updated_at": now,
    }
    if checkout_id:
        doc["checkout_id"] = checkout_id
    if paid_online and paid_online.get("provider"):
        doc["payment"] = {k: paid_online.get(k) for k in ("provider", "reference", "payment_id", "at")}
    if promo_code:
        doc["promo_code"] = promo_code
        doc["promo_discount_cents"] = discount
    return doc
