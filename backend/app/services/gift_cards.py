"""Gift cards: an album offered to someone.

The buyer picks a format and a page count (and writes a few words for the
card); the card's value is that album's price with the delivery included.
They get the card as a PDF (never printed by us) with a code. Whoever
enters the code on the site gets its value as credit on their account
(an "avoir"), and an album to create in the offered format; the credit is
taken off what they order — a dearer album is paid the difference, and
whatever a cheaper one leaves stays on the account for a next order.

A card is valid GIFT_VALIDITY_DAYS from its purchase; the credit it gives
keeps that same end date."""
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO

from reportlab.lib.pagesizes import A6, landscape
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from app.config import FRONTEND_URL
from app.db import db
from app.services.pricing import PAGE_TIERS, SHIPPING_PRICE_CENTS, compute_order_price_cents

logger = logging.getLogger(__name__)

GIFT_VALIDITY_DAYS = 365
# No 0/O, 1/I/L: a code copied from a card by hand can't be misread.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_PREFIX = "EVER"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def gift_value_cents(size: str, page_tier: int) -> int:
    """What a card is worth (and costs): the offered album, delivery included."""
    return compute_order_price_cents(size, page_tier) + SHIPPING_PRICE_CENTS


def valid_choice(size: str, page_tier: int) -> bool:
    return size in ("A4", "A5") and page_tier in PAGE_TIERS


def new_code() -> str:
    part = lambda: "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))  # noqa: E731
    return f"{CODE_PREFIX}-{part()}-{part()}"


def normalize_code(text: str) -> str:
    """As typed (lowercase, spaces, missing dashes…) → EVER-XXXX-XXXX."""
    raw = "".join(ch for ch in str(text or "").upper() if ch.isalnum())
    if raw.startswith(CODE_PREFIX):
        raw = raw[len(CODE_PREFIX):]
    return f"{CODE_PREFIX}-{raw[:4]}-{raw[4:8]}" if len(raw) == 8 else ""


async def create_gift_card(buyer: dict, item: dict, checkout_id: str, payment: dict) -> dict:
    now = _now()
    for _ in range(5):
        card = {
            "id": str(uuid.uuid4()),
            "code": new_code(),
            "buyer_user_id": buyer["id"],
            "buyer_email": buyer.get("email"),
            "size": item["size"],
            "page_tier": int(item["page_tier"]),
            "value_cents": gift_value_cents(item["size"], int(item["page_tier"])),
            "recipient_name": item.get("recipient_name") or "",
            "message": item.get("message") or "",
            "from_name": item.get("from_name") or "",
            "lang": item.get("lang") or "en",
            # Paid through the payment step (a placeholder for now, see
            # services/payments.py): usable at once.
            "status": "active" if payment.get("status") == "paid" else "pending_payment",
            "payment": payment,
            "checkout_id": checkout_id,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=GIFT_VALIDITY_DAYS)).isoformat(),
        }
        if not await db.gift_cards.find_one({"code": card["code"]}, {"_id": 1}):
            await db.gift_cards.insert_one(card)
            card.pop("_id", None)
            return card
    raise RuntimeError("Could not make a unique gift card code")


class GiftCardError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason  # not_found | not_paid | expired | used | cancelled


async def redeem(user: dict, code: str) -> dict:
    """Puts the card's value on the user's account. The same person entering
    their code again just gets their card back."""
    card = await db.gift_cards.find_one({"code": normalize_code(code)}, {"_id": 0})
    if not card:
        raise GiftCardError("not_found")
    if card.get("redeemed_by") == user["id"]:
        return card
    if card["status"] == "cancelled":
        raise GiftCardError("cancelled")
    if card["status"] == "redeemed":
        raise GiftCardError("used")
    if card["status"] != "active":
        raise GiftCardError("not_paid")
    if card["expires_at"] < _now().isoformat():
        raise GiftCardError("expired")
    now = _now().isoformat()
    # Only one person can take it, even when two try at the same moment.
    taken = await db.gift_cards.update_one(
        {"id": card["id"], "status": "active"},
        {"$set": {"status": "redeemed", "redeemed_by": user["id"], "redeemed_at": now}},
    )
    if not taken.modified_count:
        raise GiftCardError("used")
    await add_credit(user["id"], card["value_cents"], "gift_card", card["expires_at"], gift_card_id=card["id"],
                     size=card["size"], page_tier=card["page_tier"], from_name=card.get("from_name"))
    logger.info(f"Carte cadeau {card['id']} utilisée par {user['id']}")
    return await db.gift_cards.find_one({"id": card["id"]}, {"_id": 0})


# ---------- Credit (the "avoir") ----------

async def add_credit(user_id: str, amount_cents: int, source: str, expires_at: str, **extra) -> dict:
    entry = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "amount_cents": int(amount_cents),
        "remaining_cents": int(amount_cents),
        "source": source,
        "expires_at": expires_at,
        "created_at": _now().isoformat(),
        **extra,
    }
    await db.credits.insert_one(entry)
    entry.pop("_id", None)
    return entry


async def usable_credits(user_id: str) -> list:
    """The user's credit still usable, the one ending soonest first."""
    credits = await db.credits.find(
        {"user_id": user_id, "remaining_cents": {"$gt": 0}, "expires_at": {"$gt": _now().isoformat()}}, {"_id": 0}
    ).to_list(100)
    return sorted(credits, key=lambda c: c["expires_at"])


async def credit_balance(user_id: str) -> int:
    return sum(c["remaining_cents"] for c in await usable_credits(user_id))


async def use_credit(user_id: str, amount_cents: int) -> int:
    """Takes up to amount_cents from the user's credit; returns how much
    was taken."""
    left = int(amount_cents)
    for credit in await usable_credits(user_id):
        if left <= 0:
            break
        take = min(left, credit["remaining_cents"])
        # Only if the credit still holds that much (two checkouts at once).
        done = await db.credits.update_one(
            {"id": credit["id"], "remaining_cents": {"$gte": take}}, {"$inc": {"remaining_cents": -take}}
        )
        if done.modified_count:
            left -= take
    return int(amount_cents) - left


# ---------- The card as a PDF ----------

TEXT = {
    "en": {
        "eyebrow": "GIFT CARD",
        "for": "A photo album for you, {name}",
        "for_anonymous": "A photo album for you",
        "from": "— {name}",
        "what": "A {size} album, up to {pages} pages · delivery in Lebanon included",
        "code": "YOUR CODE",
        "how": "Create your album on {site}/gift and enter this code.",
        "valid": "Valid until {date}",
    },
    "fr": {
        "eyebrow": "CARTE CADEAU",
        "for": "Un album photo pour toi, {name}",
        "for_anonymous": "Un album photo pour toi",
        "from": "— {name}",
        "what": "Un album {size} jusqu'à {pages} pages · livraison au Liban incluse",
        "code": "TON CODE",
        "how": "Crée ton album sur {site}/gift et saisis ce code.",
        "valid": "Valable jusqu'au {date}",
    },
}
_INK, _MUTED, _CORAL, _PAPER = (0.10, 0.10, 0.09), (0.45, 0.43, 0.40), (0.90, 0.42, 0.33), (0.97, 0.95, 0.92)


def _site() -> str:
    return (FRONTEND_URL or "https://everbook-album.com").replace("https://", "").replace("http://", "").rstrip("/")


def card_date(iso: str, lang: str) -> str:
    d = datetime.fromisoformat(iso)
    if lang == "fr":
        months = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
        return f"{d.day} {months[d.month - 1]} {d.year}"
    return d.strftime("%B %-d, %Y")


def render_gift_card_pdf(card: dict) -> bytes:
    """The card, A6 landscape, to print at home or send on: who it's for,
    the buyer's words, the offered album, the code and how to use it."""
    from app.services import pdf  # noqa: F401  (registers the site's fonts)

    t = TEXT.get(card.get("lang"), TEXT["en"])
    w, h = landscape(A6)
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=(w, h))
    c.setTitle("Everbook — gift card")
    c.setFillColorRGB(*_PAPER)
    c.rect(0, 0, w, h, stroke=0, fill=1)
    c.setFillColorRGB(*_CORAL)
    c.rect(0, 0, 10, h, stroke=0, fill=1)
    m = 28
    c.setFillColorRGB(*_INK)
    c.setFont("CormorantGaramond-Bold", 20)
    c.drawString(m, h - 38, "Everbook")
    c.setFillColorRGB(*_CORAL)
    c.setFont("Manrope-Bold", 7)
    c.drawRightString(w - m, h - 34, t["eyebrow"])

    y = h - 72
    c.setFillColorRGB(*_INK)
    title = t["for"].format(name=card["recipient_name"]) if card.get("recipient_name") else t["for_anonymous"]
    c.setFont("CormorantGaramond-Bold", 17)
    for line in simpleSplit(title, "CormorantGaramond-Bold", 17, w - 2 * m)[:2]:
        c.drawString(m, y, line)
        y -= 19
    if card.get("message"):
        c.setFont("CormorantGaramond-Regular", 11)
        for line in simpleSplit(f"« {card['message']} »" if card.get("lang") == "fr" else f"“{card['message']}”",
                                "CormorantGaramond-Regular", 11, w - 2 * m)[:4]:
            y -= 2
            c.drawString(m, y, line)
            y -= 11
    if card.get("from_name"):
        c.setFont("CormorantGaramond-Regular", 11)
        c.drawRightString(w - m, y - 2, t["from"].format(name=card["from_name"]))

    # The offered album, the code, how to use it.
    c.setFillColorRGB(*_MUTED)
    c.setFont("Manrope-Regular", 7.5)
    c.drawString(m, 92, t["what"].format(size=card["size"], pages=card["page_tier"]))
    c.setStrokeColorRGB(*_INK)
    c.setLineWidth(0.8)
    c.rect(m, 44, w - 2 * m, 40, stroke=1, fill=0)
    c.setFillColorRGB(*_MUTED)
    c.setFont("Manrope-Bold", 6.5)
    c.drawString(m + 10, 71, t["code"])
    c.setFillColorRGB(*_INK)
    c.setFont("Manrope-Bold", 17)
    c.drawString(m + 10, 52, card["code"])
    c.setFillColorRGB(*_MUTED)
    c.setFont("Manrope-Regular", 7)
    c.drawString(m, 28, t["how"].format(site=_site()))
    c.drawString(m, 18, t["valid"].format(date=card_date(card["expires_at"], card.get("lang"))))
    c.showPage()
    c.save()
    return out.getvalue()
