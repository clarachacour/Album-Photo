"""Promo codes: a percentage off the albums (not the delivery, not gift
cards), created in the admin. Each customer can use a code once; a code
can have a last day, and be switched off.

The customer enters it in the cart (routers/cart.py): it's kept on the
cart, taken off each album line, and written on the orders placed with it
(promo_code, promo_discount_cents) — the courier then collects the lower
total."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from app.db import db

BEIRUT = ZoneInfo("Asia/Beirut")
CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,29}$")


def normalize(code: str) -> str:
    return (code or "").strip().upper().replace(" ", "")


def today() -> str:
    """Today in Lebanon (a code's last day is a day in Lebanon)."""
    return datetime.now(BEIRUT).date().isoformat()


def discount_cents(amount_cents: int, percent: int) -> int:
    return round(amount_cents * percent / 100) if percent else 0


async def check(code: str, user_id: str):
    """(the code, None) when this customer can use it, or (the code or
    None, why not): "unknown", "inactive", "expired" or "used"."""
    promo = await db.promo_codes.find_one({"code": normalize(code)}, {"_id": 0})
    if not promo:
        return None, "unknown"
    if not promo.get("active", True):
        return promo, "inactive"
    if promo.get("ends_on") and today() > promo["ends_on"]:
        return promo, "expired"
    used = await db.orders.find_one({"user_id": user_id, "promo_code": promo["code"], "status": {"$ne": "cancelled"}}, {"_id": 1})
    if used:
        return promo, "used"
    return promo, None


async def uses(code: str) -> int:
    """How many checkouts used the code (a checkout may hold several albums)."""
    return len(await db.orders.distinct("checkout_id", {"promo_code": code, "status": {"$ne": "cancelled"}}))
