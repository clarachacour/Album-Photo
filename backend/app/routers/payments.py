"""Paying a cart online: Whish Pay (services/whish.py) or a card
(Cybersource through areeba, services/cybersource.py).

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
Whish account).

A card: checkout gets a Cybersource session for the card form, shown on
the cart page; its result (through the customer's browser) only says which
transaction to look up — confirm() reads it from Cybersource (authorized,
amount, currency, our reference), captures it if it's only authorized,
then orders the same way."""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app import config
from app.config import BACKEND_URL, FRONTEND_URL
from app.core.auth import get_current_user
from app.core.executors import run_blocking, run_email
from app.db import db
from app.services import cybersource, whish
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
    return {k: payment.get(k) for k in ("id", "provider", "status", "amount_cents", "checkout_id", "redirect_url", "created_at")}


def _record(user: dict, view: dict, address: Optional[dict], terms_version: str, provider: str) -> dict:
    """A payment as recorded before paying: what the cart holds, its total."""
    return {
        "id": str(uuid.uuid4()),
        "provider": provider,
        "external_id": str(uuid.uuid4()),
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


async def start_whish_payment(user: dict, view: dict, address: Optional[dict], terms_version: str) -> dict:
    """Records the payment and gets its Whish link: {"id", "redirect_url", …}."""
    payment = _record(user, view, address, terms_version, "whish")
    payment_id, external_id = payment["id"], payment["external_id"]
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


def card_target_origins() -> list:
    """The sites the card form may be shown on: the site, and any other
    listed (CYBS_TARGET_ORIGINS, e.g. the dev site)."""
    origins = [FRONTEND_URL.rstrip("/")] + [o.strip().rstrip("/") for o in config.CYBS_TARGET_ORIGINS.split(",") if o.strip()]
    return list(dict.fromkeys(origins))


async def start_card_payment(user: dict, view: dict, address: Optional[dict], terms_version: str, lang: str = "en") -> dict:
    """Records the payment and opens a Cybersource checkout session: {"id",
    "session", …} — the page shows the card form with the session."""
    payment = _record(user, view, address, terms_version, "card")
    await db.payments.insert_one(dict(payment))
    try:
        session = await run_blocking(lambda: cybersource.create_session(
            view["total_cents"], card_target_origins(), payment["id"], "fr_FR" if lang == "fr" else "en_US"))
    except cybersource.CybersourceError as e:
        logger.error(f"Paiement {payment['id']} : session carte non créée ({e})")
        await db.payments.update_one({"id": payment["id"]}, {"$set": {"status": "not_started", "error": e.code}})
        raise HTTPException(status_code=502, detail="Card payment can't be reached right now — please try again in a moment")
    logger.info(f"Paiement {payment['id']} : session carte créée, {view['total_cents'] / 100:.2f} USD")
    return {**_public(payment), "session": session}


async def _card_status(payment: dict) -> str:
    """"success", "pending", "failed" — or "mismatch" (paid, but not what
    this payment is: amount, currency, reference) — from Cybersource."""
    transaction_id = payment.get("transaction_id")
    if not transaction_id and payment.get("status") == "pending":
        # The browser never sent the result back (page closed): looked for
        # at Cybersource with our reference, a few minutes on.
        try:
            age = _now() - datetime.fromisoformat(payment["created_at"])
        except (KeyError, TypeError, ValueError):
            age = timedelta(0)
        if age > timedelta(minutes=5):
            transaction_id = await run_blocking(cybersource.find_by_reference, payment["id"])
            if transaction_id:
                await db.payments.update_one({"id": payment["id"], "transaction_id": {"$exists": False}},
                                             {"$set": {"transaction_id": transaction_id}})
                logger.info(f"Paiement {payment['id']} : transaction carte {transaction_id} retrouvée par la référence")
    if not transaction_id:
        return "pending"
    tx = await run_blocking(cybersource.transaction, transaction_id)
    if tx is None:
        return "pending"  # not listed yet: it takes a few seconds
    info = cybersource.read_transaction(tx)
    logger.info(f"Paiement {payment['id']} : transaction carte {transaction_id} — {info}")
    if info["declined"]:
        return "failed"
    if not info["authorized"]:
        return "pending"
    if (info["amount_cents"] != payment["amount_cents"] or info["currency"] != "USD"
            or (info["reference"] and info["reference"] != payment["id"])):
        return "mismatch"
    if not info["captured"]:
        # An authorization only holds the money: it's collected now.
        await run_blocking(cybersource.capture, transaction_id, payment["amount_cents"], payment["id"])
        logger.info(f"Paiement {payment['id']} : transaction {transaction_id} autorisée seulement — encaissement demandé")
    return "success"


async def _provider_status(payment: dict) -> str:
    if payment.get("provider") == "card":
        return await _card_status(payment)
    return await run_blocking(whish.payment_status, payment["external_id"])


async def confirm(payment: dict, attempt_failed: bool = False, background: Optional[BackgroundTasks] = None) -> dict:
    """Asks Whish where the payment stands and acts on it (see the module's
    docstring). Returns the payment as it is now.

    attempt_failed: Whish said the attempt failed (failure callback, or the
    customer sent back to the failure page). Whish keeps such a payment
    "pending" until its link expires, but a link takes one attempt only:
    it's then marked failed here — unless Whish says it's paid. A "failed"
    payment is still looked at again (by the scheduled check): paid after
    all, it's ordered.

    background: the request's background tasks, when a customer waits on
    the answer — the albums' PDFs are then started after it's sent."""
    if payment.get("status") not in ("pending", "failed"):
        return payment
    try:
        status = await _provider_status(payment)
    except (whish.WhishError, cybersource.CybersourceError) as e:
        logger.warning(f"Paiement {payment['id']} : statut non lu ({e.code})")
        return payment
    now = _now().isoformat()
    if status == "mismatch":
        claimed = await db.payments.update_one({"id": payment["id"], "status": {"$in": ["pending", "failed"]}},
                                               {"$set": {"status": "needs_review", "problem": "the card transaction doesn't match this payment"}})
        if claimed.modified_count:
            user = await db.users.find_one({"id": payment["user_id"]}, {"_id": 0}) or {}
            await run_email(send_payment_review_email, {**payment, "paid_at": now}, user,
                            f"the card transaction {payment.get('transaction_id')} doesn't match this payment")
    elif status == "success":
        # Claimed first: only one caller (callback, return page, scheduled
        # check) goes on to order.
        claimed = await db.payments.update_one({"id": payment["id"], "status": {"$in": ["pending", "failed"]}},
                                               {"$set": {"status": "placing", "paid_at": now}})
        if claimed.modified_count:
            await _place(payment, now, background)
    elif status in ("failed", "refunded") or attempt_failed:
        await db.payments.update_one({"id": payment["id"], "status": "pending"}, {"$set": {"status": "failed", "checked_at": now}})
    else:
        await db.payments.update_one({"id": payment["id"], "status": {"$in": ["pending", "failed"]}}, {"$set": {"checked_at": now}})
    return await db.payments.find_one({"id": payment["id"]}, {"_id": 0})


async def _place(payment: dict, paid_at: str, background: Optional[BackgroundTasks] = None):
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
                "status": "paid", "provider": payment.get("provider") or "whish",
                "reference": payment.get("transaction_id") or payment["external_id"], "payment_id": payment["id"],
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
                if background is not None:
                    background.add_task(start_order_pdf_generation, order)
                else:
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


class CardResult(BaseModel):
    # The card form's result (a JWT), or the customer closing it.
    result: Optional[str] = Field(default=None, max_length=20000)
    cancelled: bool = False
    # Why the card form closed, when it failed rather than being closed by
    # the customer (the SDK's message: for the logs only).
    error: Optional[str] = Field(default=None, max_length=1000)


@router.post("/payments/{payment_id}/card")
async def card_result(payment_id: str, data: CardResult, background: BackgroundTasks, user: dict = Depends(get_current_user)):
    """The card form is done: its result names the transaction, which is
    then checked with Cybersource (confirm) — the result itself is never
    taken as proof of payment."""
    payment = await db.payments.find_one({"id": payment_id, "user_id": user["id"], "provider": "card"}, {"_id": 0})
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if data.cancelled or not data.result:
        if data.error:
            logger.warning(f"Paiement {payment_id} : formulaire carte en échec côté site ({data.error}), sites autorisés {card_target_origins()}")
        await db.payments.update_one({"id": payment_id, "status": "pending", "transaction_id": {"$exists": False}},
                                     {"$set": {"status": "cancelled"}})
        return _public(await db.payments.find_one({"id": payment_id}, {"_id": 0}))
    transaction_id = cybersource.result_transaction_id(data.result)
    if not transaction_id:
        raise HTTPException(status_code=400, detail="Unreadable card payment result")
    # One transaction pays for one payment only.
    if await db.payments.find_one({"transaction_id": transaction_id, "id": {"$ne": payment_id}}, {"_id": 1}):
        raise HTTPException(status_code=409, detail="This card payment was already used")
    await db.payments.update_one({"id": payment_id, "transaction_id": {"$exists": False}}, {"$set": {"transaction_id": transaction_id}})
    payment = await db.payments.find_one({"id": payment_id}, {"_id": 0})
    if payment.get("transaction_id") != transaction_id:
        raise HTTPException(status_code=409, detail="This payment already has a card transaction")
    payment = await confirm(payment, background=background)
    return _public(payment)


@router.get("/payments/{payment_id}")
async def get_payment(payment_id: str, background: BackgroundTasks, outcome: str = Query(""), user: dict = Depends(get_current_user)):
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
        payment = await confirm(payment, outcome == "failure", background)
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
