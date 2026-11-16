"""Paying a cart with Whish Pay (services/whish.py).

1. Checkout (routers/cart.py) calls start_whish_payment: a payment is
   recorded (db.payments) with what the cart holds and its total, Whish
   gives a payment link, the customer is sent there. Nothing is ordered.
2. The customer pays in the Whish app (QR code or six-digit code), or not.
   Whish calls our callback, and sends the customer back to
   /payment/return on the site, which asks GET /payments/{id}.
3. Either way, confirm() asks Whish for the payment's real status (a
   callback is only a signal): paid → the cart is ordered (place_checkout)
   — once, whoever gets there first; failed or expired → nothing ordered,
   the cart is still there to try again.
4. A payment nobody came back for is checked by the scheduled job
   (reconcile_payments, /internal/sync-deliveries).

If the cart changed between paying and ordering (another tab), nothing is
ordered on a guess: the payment is marked "needs_review" and the team is
emailed to sort it out with the customer (order by hand or refund in the
Whish account)."""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.config import BACKEND_URL, FRONTEND_URL
from app.core.auth import get_current_user
from app.core.executors import run_blocking, run_email
from app.db import db
from app.services import whish
from app.services.email import send_payment_review_email
from app.services.orders import start_order_pdf_generation

router = APIRouter()
logger = logging.getLogger(__name__)

# Not checked with Whish more often than this for the same payment (the
# return page asks every few seconds).
RECHECK_SECONDS = 4
# A payment link lasts 5 minutes; past this, a payment still "pending" is
# given up (nothing ordered, nothing charged).
GIVE_UP_AFTER = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cart_signature(view: dict) -> list:
    """What was paid for: each cart line and its quantity."""
    return sorted(f"{line['id']}:{line['quantity']}" for line in view["items"])


def _public(payment: dict) -> dict:
    return {k: payment.get(k) for k in ("id", "status", "amount_cents", "checkout_id", "redirect_url", "created_at")}


async def start_whish_payment(user: dict, view: dict, address: Optional[dict], terms_version: str) -> dict:
    """Records the payment and gets its Whish link: {"id", "redirect_url", …}."""
    payment_id = str(uuid.uuid4())
    external_id = str(uuid.uuid4())
    payment = {
        "id": payment_id,
        "provider": "whish",
        "external_id": external_id,
        "user_id": user["id"],
        "amount_cents": view["total_cents"],
        "currency": "usd",
        "status": "pending",
        "cart": _cart_signature(view),
        "promo_code": (view.get("promo") or {}).get("code"),
        "shipping_address": address,
        "accepted_terms_version": terms_version,
        "checkout_id": str(uuid.uuid4()),
        "created_at": _now().isoformat(),
    }
    await db.payments.insert_one(dict(payment))
    names = [line.get("album", {}).get("title") or ("Gift card" if line["kind"] == "gift" else "Album") for line in view["items"]]
    invoice = "Everbook — " + ", ".join(names)
    back = f"{FRONTEND_URL}/payment/return?payment={payment_id}"
    callback = f"{BACKEND_URL}/api/payments/whish/callback?payment={payment_id}"
    try:
        url = await run_blocking(lambda: whish.create_payment(
            amount_cents=view["total_cents"], external_id=external_id, invoice=invoice,
            success_callback=f"{callback}&outcome=success", failure_callback=f"{callback}&outcome=failure",
            success_redirect=f"{back}&outcome=success", failure_redirect=f"{back}&outcome=failure",
        ))
    except whish.WhishError as e:
        logger.error(f"Paiement {payment_id} : lien Whish non créé ({e.code})")
        await db.payments.update_one({"id": payment_id}, {"$set": {"status": "not_started", "error": e.code}})
        raise HTTPException(status_code=502, detail="Whish Pay can't be reached right now — please try again in a moment")
    await db.payments.update_one({"id": payment_id}, {"$set": {"redirect_url": url}})
    logger.info(f"Paiement {payment_id} : lien Whish créé, {view['total_cents'] / 100:.2f} USD")
    return _public({**payment, "redirect_url": url})


async def confirm(payment: dict, attempt_failed: bool = False) -> dict:
    """Asks Whish where the payment stands and acts on it (see the module's
    docstring). Returns the payment as it is now.

    attempt_failed: Whish said the attempt failed (failure callback, or the
    customer sent back to the failure page). Whish keeps such a payment
    "pending" until its link expires, but a link takes one attempt only:
    it's then marked failed here — unless Whish says it's paid. A "failed"
    payment is still looked at again (by the scheduled check): paid after
    all, it's ordered."""
    if payment.get("status") not in ("pending", "failed"):
        return payment
    try:
        status = await run_blocking(whish.payment_status, payment["external_id"])
    except whish.WhishError as e:
        logger.warning(f"Paiement {payment['id']} : statut Whish non lu ({e.code})")
        return payment
    now = _now().isoformat()
    if status == "success":
        # Claimed first: only one caller (callback, return page, scheduled
        # check) goes on to order.
        claimed = await db.payments.update_one({"id": payment["id"], "status": {"$in": ["pending", "failed"]}},
                                               {"$set": {"status": "placing", "paid_at": now}})
        if claimed.modified_count:
            await _place(payment, now)
    elif status in ("failed", "refunded") or attempt_failed:
        await db.payments.update_one({"id": payment["id"], "status": "pending"}, {"$set": {"status": "failed", "checked_at": now}})
    else:
        await db.payments.update_one({"id": payment["id"], "status": {"$in": ["pending", "failed"]}}, {"$set": {"checked_at": now}})
    return await db.payments.find_one({"id": payment["id"]}, {"_id": 0})


async def _place(payment: dict, paid_at: str):
    """The cart, as paid for, becomes orders — or, if it changed, a review."""
    from app.routers.cart import _view, place_checkout

    user = await db.users.find_one({"id": payment["user_id"]}, {"_id": 0})
    problem = None
    view = await _view(user) if user else None
    if not view:
        problem = "account not found"
    elif _cart_signature(view) != payment["cart"]:
        problem = "the cart changed after the payment"
    elif view["total_cents"] != payment["amount_cents"]:
        problem = f"the cart's total is now {view['total_cents'] / 100:.2f} USD"
    elif any(line["problem"] for line in view["items"]):
        problem = "something in the cart can't be ordered any more"
    if problem is None:
        try:
            result = await place_checkout(user, view, payment.get("shipping_address"), paid={
                "status": "paid", "provider": "whish", "reference": payment["external_id"], "payment_id": payment["id"],
                "amount_cents": payment["amount_cents"], "at": paid_at, "checkout_id": payment["checkout_id"],
            }, start_pdfs=False)
            await db.payments.update_one({"id": payment["id"]}, {"$set": {
                "status": "placed", "order_ids": [o["id"] for o in result["orders"]],
                "gift_card_ids": [c["id"] for c in result["gift_cards"]],
            }})
        except Exception as e:
            problem = f"ordering failed: {getattr(e, 'detail', None) or e}"
        else:
            # Recorded as ordered first (the customer's page shows it), then
            # each album's PDF (through the Cloud Tasks queue when configured).
            for order in result["orders"]:
                await start_order_pdf_generation(order)
            return
    logger.error(f"Paiement {payment['id']} payé mais non commandé : {problem}")
    await db.payments.update_one({"id": payment["id"]}, {"$set": {"status": "needs_review", "problem": problem}})
    await run_email(send_payment_review_email, {**payment, "paid_at": paid_at}, user or {}, problem)


@router.get("/payments/whish/callback", response_class=PlainTextResponse)
async def whish_callback(background: BackgroundTasks, payment: str = Query(...), outcome: str = Query("")):
    """Whish's call after a payment attempt (server to server, GET). Only a
    signal: the status is read from Whish itself (confirm), after
    answering — ordering can take a moment, Whish isn't kept waiting."""
    found = await db.payments.find_one({"id": payment}, {"_id": 0})
    if found:
        logger.info(f"Paiement {payment} : rappel Whish ({outcome or '?'})")
        background.add_task(confirm, found, outcome == "failure")
    return "OK"


@router.get("/payments/{payment_id}")
async def get_payment(payment_id: str, outcome: str = Query(""), user: dict = Depends(get_current_user)):
    """Where the customer's payment stands (the site's return page asks
    until it's settled): pending, placed, failed, needs_review. outcome:
    where Whish sent the customer back ("failure": the attempt failed)."""
    payment = await db.payments.find_one({"id": payment_id, "user_id": user["id"]}, {"_id": 0})
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    last = payment.get("checked_at") or payment.get("created_at")
    try:
        recent = _now() - datetime.fromisoformat(last) < timedelta(seconds=RECHECK_SECONDS)
    except (TypeError, ValueError):
        recent = False
    if payment["status"] == "pending" and (not recent or outcome == "failure"):
        payment = await confirm(payment, outcome == "failure")
    out = _public(payment)
    if payment["status"] == "placed":
        # What was ordered, to show on the return page.
        out["orders"] = await db.orders.find({"id": {"$in": payment.get("order_ids") or []}}, {"_id": 0}).to_list(50)
        out["gift_cards"] = await db.gift_cards.find({"id": {"$in": payment.get("gift_card_ids") or []}}, {"_id": 0}).to_list(50)
    return out


async def reconcile_payments() -> dict:
    """The scheduled check: payments still pending (no callback came, the
    customer closed the page) are confirmed with Whish; past a day,
    given up."""
    now = _now()
    confirmed = given_up = 0
    recent = (now - GIVE_UP_AFTER).isoformat()
    # Pending ones, and failed ones of the last day (paid after all?).
    async for payment in db.payments.find({"$or": [{"status": "pending"}, {"status": "failed", "created_at": {"$gt": recent}}]}, {"_id": 0}):
        try:
            created = datetime.fromisoformat(payment["created_at"])
        except (KeyError, TypeError, ValueError):
            created = now
        before = payment["status"]
        after = await confirm(payment)
        if after.get("status") != before:
            confirmed += 1
        elif before == "pending" and now - created > GIVE_UP_AFTER:
            await db.payments.update_one({"id": payment["id"], "status": "pending"}, {"$set": {"status": "expired"}})
            given_up += 1
    # Stuck halfway (the server stopped while ordering): the team checks.
    stuck_before = (now - timedelta(minutes=15)).isoformat()
    async for payment in db.payments.find({"status": "placing", "paid_at": {"$lt": stuck_before}}, {"_id": 0}):
        claimed = await db.payments.update_one({"id": payment["id"], "status": "placing"},
                                               {"$set": {"status": "needs_review", "problem": "ordering didn't finish"}})
        if claimed.modified_count:
            user = await db.users.find_one({"id": payment["user_id"]}, {"_id": 0}) or {}
            await run_email(send_payment_review_email, payment, user, "ordering didn't finish")
    return {"payments_settled": confirmed, "payments_expired": given_up}
