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
) -> dict:
    """A new order, priced on the server. `shipping`: what this order pays
    for delivery (a cart's printed albums pay it once, on the first)."""
    digital = kind == "digital"
    unit_price = unit_price_cents(album, kind)
    quantity = 1 if digital else quantity
    # No combined price: the PDF and the printed book of the same album are
    # each at their own price.
    credit = 0
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
        "total_price_cents": unit_price * quantity + shipping - credit,
        "terms_version": TERMS_VERSION,
        "terms_accepted_at": now,
        "currency": "usd",
        "shipping_address": shipping_address if not digital else None,
        # A digital album: online payment isn't set up yet, so it's handed
        # over at once — the PDF is sent as soon as it's made, with nothing
        # to do on the admin side. A printed one is paid in cash to the
        # courier.
        "status": "paid" if digital else "pending_payment",
        # No credit on a printed copy for a PDF nobody paid for.
        "handed_over_unpaid": digital,
        "status_history": [{"status": "paid" if digital else "pending_payment", "at": now}],
        "pdf_ready": False,
        "pdf_path": None,
        "tracking_number": None,
        "created_at": now,
        "updated_at": now,
    }
    if checkout_id:
        doc["checkout_id"] = checkout_id
    return doc
