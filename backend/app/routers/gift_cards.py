"""Gift cards (see services/gift_cards.py): bought through the cart; here,
entering a code, the credit it gives, the cards bought, and the admin's
list."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.core.auth import get_current_user, is_admin, require_admin
from app.core.rate_limit import rate_limiter
from app.core.security import client_ip
from app.db import db
from app.schemas import GiftCodeInput
from app.services import gift_cards

router = APIRouter()

# Codes can't be guessed by trying many (per account and per address).
REDEEM_LIMIT_PER_USER = (10, 60 * 60)
REDEEM_LIMIT_PER_IP = (30, 60 * 60)

# What the person who received a card sees of it (not who paid, nor how).
PUBLIC_FIELDS = ("code", "size", "page_tier", "value_cents", "recipient_name", "message", "from_name", "expires_at", "status")


def _public(card: dict) -> dict:
    return {k: card.get(k) for k in PUBLIC_FIELDS}


@router.post("/gift-cards/redeem")
async def redeem_gift_card(data: GiftCodeInput, request: Request, user: dict = Depends(get_current_user)):
    await rate_limiter.check_all([
        ("gift:user", user["id"], *REDEEM_LIMIT_PER_USER),
        ("gift:ip", client_ip(request), *REDEEM_LIMIT_PER_IP),
    ])
    try:
        card = await gift_cards.redeem(user, data.code)
    except gift_cards.GiftCardError as e:
        messages = {
            "not_found": "This code doesn't exist — please check it",
            "used": "This gift card has already been used",
            "expired": "This gift card has expired",
            "cancelled": "This gift card was cancelled",
            "not_paid": "This gift card can't be used yet",
        }
        raise HTTPException(status_code=404 if e.reason == "not_found" else 409,
                            detail={"reason": e.reason, "message": messages[e.reason]})
    return {"gift_card": _public(card), "credit_balance_cents": await gift_cards.credit_balance(user["id"])}


@router.get("/credits")
async def my_credit(user: dict = Depends(get_current_user)):
    """The customer's credit (from gift cards), and the album offered by the
    latest card still with credit on it — to start creating it."""
    credits = await gift_cards.usable_credits(user["id"])
    offered = next((c for c in sorted(credits, key=lambda c: c["created_at"], reverse=True) if c.get("size")), None)
    return {
        "balance_cents": sum(c["remaining_cents"] for c in credits),
        "credits": [{k: c.get(k) for k in ("id", "amount_cents", "remaining_cents", "source", "expires_at", "size", "page_tier", "from_name")} for c in credits],
        "offered": {"size": offered["size"], "page_tier": offered["page_tier"], "from_name": offered.get("from_name")} if offered else None,
    }


@router.get("/gift-cards")
async def my_gift_cards(user: dict = Depends(get_current_user)):
    """The gift cards the customer bought."""
    cards = await db.gift_cards.find({"buyer_user_id": user["id"]}, {"_id": 0, "payment": 0}).sort("created_at", -1).to_list(200)
    return cards


@router.get("/gift-cards/{card_id}/pdf")
async def gift_card_pdf(card_id: str, user: dict = Depends(get_current_user)):
    card = await db.gift_cards.find_one({"id": card_id}, {"_id": 0})
    if not card or (card["buyer_user_id"] != user["id"] and not is_admin(user)):
        raise HTTPException(status_code=404, detail="Gift card not found")
    pdf = gift_cards.render_gift_card_pdf(card)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="Everbook gift card {card["code"]}.pdf"'})


@router.get("/admin/gift-cards")
async def admin_gift_cards(user: dict = Depends(get_current_user)):
    require_admin(user)
    return await db.gift_cards.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/admin/gift-cards/{card_id}/cancel")
async def admin_cancel_gift_card(card_id: str, user: dict = Depends(get_current_user)):
    """A card not used yet can be cancelled (e.g. refunded): its code no
    longer works."""
    require_admin(user)
    done = await db.gift_cards.update_one({"id": card_id, "status": {"$in": ["active", "pending_payment"]}}, {"$set": {"status": "cancelled"}})
    if not done.modified_count:
        raise HTTPException(status_code=409, detail="Only a gift card not used yet can be cancelled")
    return await db.gift_cards.find_one({"id": card_id}, {"_id": 0})
