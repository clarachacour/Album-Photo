"""Online payment: by card, through Cybersource Unified Checkout (areeba).

A card payment is a document in db.payments, made when the customer opens
the card form (start_card_payment) for the amount their cart comes to then,
and charged when they place the order (charge_card). The charge is refused
when the cart changed in between (another amount, another album…): the
customer opens the form again.

Statuses: "open" (form shown) → "charging" (one request at a time) →
"paid" | "failed" | "unknown" (Cybersource didn't answer: the team checks
in the Business Center). A payment taken for orders that couldn't be placed
after all is marked "refund_needed" and the team is told.

Whish Pay: not offered yet. Without online payment, printed albums are paid
cash on delivery (the courier collects the total), and what can't be — the
PDF and gift cards, with nothing delivered — is shown as "coming soon"."""
import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.core.executors import run_blocking, run_email
from app.db import db
from app.services import cybersource

logger = logging.getLogger(__name__)

ONLINE_PAYMENT = cybersource.configured()
NEEDS_ONLINE_PAYMENT = "Coming soon: the PDF and gift cards will be available with Whish Pay and card payment"
NEEDS_CARD = "The PDF and gift cards are paid by card"

# A capture context (and the transient token made from it) is good for 15
# minutes at Cybersource; a bit less here.
CARD_SESSION_MINUTES = 14


class PaymentError(Exception):
    """The card payment can't go on. `code`: the HTTP status to answer."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> datetime:
    return datetime.now(timezone.utc)


def cart_fingerprint(view: dict) -> str:
    """What a payment was opened for: the amount and every line of the
    cart, so a cart changed after the card form opened isn't charged."""
    lines = sorted((i.get("id"), i.get("kind"), i.get("quantity"), i.get("line_total_cents")) for i in view["items"])
    key = json.dumps([view["total_cents"], (view.get("promo") or {}).get("code"), lines], default=str)
    return hashlib.sha256(key.encode()).hexdigest()


async def start_card_payment(user: dict, view: dict, lang: str = "en") -> dict:
    """Opens a card payment for the cart's total: {payment_id,
    capture_context, amount_cents}."""
    amount = int(view["total_cents"])
    if amount <= 0:
        raise PaymentError(400, "Nothing to pay by card")
    try:
        context = await run_blocking(cybersource.capture_context, amount, lang)
    except cybersource.GatewayError as exc:
        logger.error(f"Paiement carte : contexte refusé — {exc}")
        raise PaymentError(502, "Card payment isn't available right now — please try again in a moment")
    now = _now()
    payment = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "method": "card",
        "provider": "cybersource",
        "amount_cents": amount,
        "currency": "usd",
        "fingerprint": cart_fingerprint(view),
        "status": "open",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=CARD_SESSION_MINUTES)).isoformat(),
    }
    await db.payments.insert_one(payment)
    return {"payment_id": payment["id"], "capture_context": context, "amount_cents": amount}


def _bill_to(user: dict, address: dict = None) -> dict:
    address = address or {}
    name = (address.get("full_name") or user.get("name") or "").strip().split()
    return {
        "firstName": name[0] if name else "",
        "lastName": " ".join(name[1:]) if len(name) > 1 else (name[0] if name else ""),
        "email": user.get("email") or "",
        "address1": address.get("street") or "",
        "locality": address.get("city") or "",
        "country": "LB",
        "phoneNumber": address.get("phone") or "",
    }


async def charge_card(user: dict, payment_id: str, transient_token: str, view: dict, address: dict = None) -> dict:
    """Charges the card for the cart as it is now. Returns what an order
    keeps of it: {"status": "paid", "method", "provider", "reference",
    "payment_id", "amount_cents", "at"}. Raises PaymentError otherwise."""
    payment = await db.payments.find_one({"id": payment_id or "", "user_id": user["id"]}, {"_id": 0})
    if not payment:
        raise PaymentError(400, "Please enter your card again")
    if payment["status"] == "paid":
        raise PaymentError(409, "This payment was already made")
    if payment["status"] != "open" or payment["expires_at"] < _now().isoformat():
        raise PaymentError(400, "Please enter your card again")
    if payment["fingerprint"] != cart_fingerprint(view) or payment["amount_cents"] != view["total_cents"]:
        raise PaymentError(409, "Your cart changed — please check it and enter your card again")
    # One charge per payment, even with two clicks or two tabs.
    claimed = await db.payments.update_one({"id": payment_id, "status": "open"},
                                           {"$set": {"status": "charging", "charging_at": _now().isoformat()}})
    if not claimed.modified_count:
        raise PaymentError(409, "This payment is already being processed")
    try:
        result = await run_blocking(cybersource.authorize_and_capture, transient_token, payment["amount_cents"],
                                    payment_id, _bill_to(user, address))
    except cybersource.GatewayError as exc:
        status = "unknown" if exc.sent else "failed"
        await db.payments.update_one({"id": payment_id}, {"$set": {"status": status, "error": str(exc)}})
        logger.error(f"Paiement carte {payment_id} ({status}) : {exc}")
        if exc.sent:
            await _tell_team(payment, "Cybersource didn't answer: check in the Business Center whether the card was charged.")
            raise PaymentError(502, "We couldn't confirm your payment. Please don't pay again: we'll check and contact you.")
        raise PaymentError(502, "Card payment isn't available right now — nothing was charged, please try again")
    at = _now().isoformat()
    if not result["approved"]:
        # AUTHORIZED but for another amount: the card was charged anyway.
        charged = result["status"] == "AUTHORIZED"
        await db.payments.update_one({"id": payment_id}, {"$set": {
            "status": "refund_needed" if charged else "failed", "gateway": result["raw"], "transaction_id": result["id"], "at": at}})
        logger.warning(f"Paiement carte {payment_id} refusé : {result['status']} {result['reason']} {result['message']}")
        if charged:
            await _tell_team(payment, f"Authorized for another amount than {payment['amount_cents'] / 100:.2f} USD: refund it.")
        raise PaymentError(402, "Your card was declined — nothing was ordered. Please check your card details or try another card.")
    await db.payments.update_one({"id": payment_id}, {"$set": {
        "status": "paid", "transaction_id": result["id"], "gateway": result["raw"], "at": at}})
    logger.info(f"Paiement carte {payment_id} : {payment['amount_cents'] / 100:.2f} USD encaissé ({result['id']})")
    return {"status": "paid", "method": "card", "provider": "cybersource", "reference": result["id"],
            "payment_id": payment_id, "amount_cents": payment["amount_cents"], "at": at}


async def refund_needed(payment: dict, reason: str):
    """A card payment taken for orders that couldn't be placed after all
    (ordered meanwhile in another tab): the team refunds it."""
    await db.payments.update_one({"id": payment["payment_id"]}, {"$set": {"status": "refund_needed", "refund_reason": reason}})
    logger.error(f"Paiement carte {payment['payment_id']} à rembourser : {reason}")
    stored = await db.payments.find_one({"id": payment["payment_id"]}, {"_id": 0})
    await _tell_team(stored or payment, f"Refund needed: {reason}")


async def _tell_team(payment: dict, what: str):
    from app.services.email import send_team_payment_problem_email

    customer = await db.users.find_one({"id": payment.get("user_id")}, {"_id": 0, "email": 1, "name": 1}) or {}
    await run_email(send_team_payment_problem_email, payment, customer, what)
