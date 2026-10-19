"""Albums ordered together go to the printer together: one email, one
"ready" click, one Wakilni delivery.

A printed order whose PDF is made waits a little (GROUP_DELAY_SECONDS)
before the printer hears about it; the customer's other printed orders to
the same address waiting by then go in the same email. The first one
leads the group: its number goes on the package (Wakilni's waybill), its
links are the printer's. The delivery is paid once: the other orders of
the group no longer pay it.

The printer email goes out from flush_printer_queue, run by the scheduler
every 30 minutes with the delivery follow-up (/internal/sync-deliveries).
"""
import logging
import unicodedata
from datetime import datetime, timedelta, timezone

from app.core.executors import run_email
from app.db import db
from app.services.email import send_printer_order_email

logger = logging.getLogger(__name__)

GROUP_DELAY_SECONDS = 3600


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _norm(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return "".join(ch for ch in text if ch.isalnum())


def address_key(order: dict) -> tuple:
    """Same customer, same place: one delivery."""
    a = order.get("shipping_address") or {}
    return (order.get("user_id"),) + tuple(_norm(a.get(k)) for k in ("phone", "street", "building", "area", "city"))


async def group_of(order: dict) -> list:
    """The orders going to the printer and to the customer with this one,
    lead first (just this one when it isn't in a group). Cancelled ones
    are left out."""
    lead_id = order.get("print_group") or order["id"]
    members = await db.orders.find({"print_group": lead_id, "status": {"$ne": "cancelled"}}, {"_id": 0}).to_list(50)
    if not members:
        return [order]
    members.sort(key=lambda o: (o["id"] != lead_id, o.get("created_at") or ""))
    return members


async def queue_for_printer(order_id: str):
    """The PDF is made: the printer hears about it with the next flush once
    the delay is over (with the customer's other orders by then)."""
    await db.orders.update_one({"id": order_id}, {"$set": {"printer_pending_at": _now().isoformat()}})


# A cart's printed album whose PDF takes long (a big album) is waited for,
# so they all go together — but not forever (a PDF that keeps failing).
CART_WAIT_MAX_SECONDS = 24 * 3600


async def _cart_still_making(orders: list) -> bool:
    """Whether a printed album ordered in the same cart as these still has
    its PDF being made."""
    checkouts = {o["checkout_id"] for o in orders if o.get("checkout_id")}
    if not checkouts:
        return False
    since = (_now() - timedelta(seconds=CART_WAIT_MAX_SECONDS)).isoformat()
    waiting = await db.orders.find_one({
        "checkout_id": {"$in": list(checkouts)},
        "id": {"$nin": [o["id"] for o in orders]},
        "kind": "print",
        "status": "pending_payment",
        "pdf_ready": False,
        "pdf_error": {"$in": [None, ""]},
        "created_at": {"$gte": since},
    }, {"_id": 1})
    return waiting is not None


async def flush_printer_queue(force_order_id: str = None) -> int:
    """Sends the printer one email per group whose wait is over (or the
    group of force_order_id, at once). Returns the number of emails."""
    pending = await db.orders.find(
        {"printer_pending_at": {"$exists": True}, "status": "printing"}, {"_id": 0}
    ).to_list(1000)
    groups = {}
    for o in pending:
        groups.setdefault(address_key(o), []).append(o)
    limit = (_now() - timedelta(seconds=GROUP_DELAY_SECONDS)).isoformat()
    sent = 0
    for orders in groups.values():
        forced = any(o["id"] == force_order_id for o in orders)
        due = min(o["printer_pending_at"] for o in orders) <= limit
        if not forced and (not due or await _cart_still_making(orders)):
            continue
        # The one paying the delivery leads (a cart's albums are created
        # together: same time).
        orders.sort(key=lambda o: (o.get("created_at") or "", -int(o.get("shipping_price_cents") or 0)))
        lead = orders[0]
        payer = next((o for o in orders if int(o.get("shipping_price_cents") or 0)), None)
        now = _now().isoformat()
        for o in orders:
            update = {"print_group": lead["id"], "printer_emailed_at": now}
            shipping = int(o.get("shipping_price_cents") or 0)
            if o is not payer and shipping:
                # One trip for the whole group: delivery paid once.
                update.update(
                    shipping_price_cents=0,
                    shipping_waived_cents=shipping,
                    total_price_cents=int(o.get("total_price_cents") or 0) - shipping,
                )
            await db.orders.update_one({"id": o["id"]}, {"$set": update, "$unset": {"printer_pending_at": ""}})
        members = await group_of({**lead, "print_group": lead["id"]})
        await run_email(send_printer_order_email, members[0], members)
        if len(members) > 1:
            logger.info(f"Commandes {', '.join(o['id'] for o in members)} : envoyées ensemble à l'imprimerie")
        sent += 1
    return sent
