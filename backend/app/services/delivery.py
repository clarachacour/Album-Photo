"""Getting a printed book to its customer: a Wakilni delivery created when
the printer marks the book ready, then followed until it's delivered (see
services/wakilni.py). Without Wakilni configured, the courier gets an
email instead, as before."""
import logging
from datetime import datetime, timezone

from app.core.executors import run_blocking, run_email
from app.db import db
from app.services import wakilni
from app.services.email import (
    send_delivery_pickup_email,
    send_delivery_problem_email,
    send_order_delivered_feedback_email,
    send_order_shipped_email,
    send_team_order_update_email,
)

logger = logging.getLogger(__name__)

# Wakilni's statuses that need someone to look (code → what to say).
PROBLEM_STATUSES = {
    wakilni.FAILED: "the delivery failed",
    wakilni.DECLINED: "Wakilni declined the delivery",
    wakilni.CANCELED: "the delivery was cancelled",
    wakilni.CLOSED_FAILED: "the delivery failed (closed)",
    wakilni.POSTPONED: "the delivery was postponed",
    wakilni.PENDING_CANCELLATION: "the delivery is being cancelled",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _set_status(order_id: str, status: str):
    now = _now()
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"status": status, "updated_at": now}, "$push": {"status_history": {"status": status, "at": now}}},
    )


async def _customer(order: dict) -> dict:
    return await db.users.find_one({"id": order["user_id"]}, {"_id": 0, "email": 1, "name": 1}) or {}


async def dispatch_delivery(order_id: str) -> dict:
    """The book is ready at the printer: a Wakilni delivery is created (once),
    or, without Wakilni, the courier is emailed. If Wakilni refuses, the
    courier is emailed too and the admin is told. Returns the order."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        return {}
    if not wakilni.configured():
        await run_email(send_delivery_pickup_email, order)
        return order
    if (order.get("delivery") or {}).get("delivery_id"):
        return order  # already created
    try:
        created = await run_blocking(wakilni.create_delivery, order, await _customer(order))
    except Exception as e:
        logger.error(f"Commande {order_id} : livraison Wakilni non créée : {e}")
        await db.orders.update_one({"id": order_id}, {"$set": {"delivery": {"provider": "wakilni", "error": str(e)[:500], "at": _now()}}})
        order = await db.orders.find_one({"id": order_id}, {"_id": 0})
        await run_email(send_delivery_problem_email, order, f"the Wakilni delivery couldn't be created ({str(e)[:200]})")
        await run_email(send_delivery_pickup_email, order)  # the courier still hears about it
        return order
    created.update(created_at=_now(), status_code=wakilni.PENDING, status_label="Pending")
    await db.orders.update_one({"id": order_id}, {"$set": {"delivery": created, "tracking_number": created.get("tracking_id")}})
    logger.info(f"Commande {order_id} : livraison Wakilni {created.get('delivery_id')} créée")
    return await db.orders.find_one({"id": order_id}, {"_id": 0})


async def sync_delivery(order_id: str) -> dict:
    """Asks Wakilni where the delivery is and follows it on the order:
    on its way → shipped (email), delivered → delivered (email), a problem →
    the admin is emailed (once per status)."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    delivery = (order or {}).get("delivery") or {}
    if not delivery.get("delivery_id") or not wakilni.configured():
        return order or {}
    status = await run_blocking(wakilni.delivery_status, delivery["delivery_id"])
    code, label = status.get("code"), status.get("label") or ""
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"delivery.status_code": code, "delivery.status_label": label, "delivery.checked_at": _now()}},
    )
    customer = None
    if code == wakilni.PROCESSING and order["status"] in ("pending_payment", "paid", "processing", "printing", "ready_for_delivery"):
        await _set_status(order_id, "shipped")
        customer = await _customer(order)
        fresh = await db.orders.find_one({"id": order_id}, {"_id": 0})
        await run_email(send_order_shipped_email, customer.get("email"), customer.get("name"), fresh)
    elif code == wakilni.SUCCESS and not status.get("rejected") and order["status"] != "delivered":
        await _set_status(order_id, "delivered")
        customer = await _customer(order)
        fresh = await db.orders.find_one({"id": order_id}, {"_id": 0})
        await run_email(send_order_delivered_feedback_email, customer.get("email"), customer.get("name"), fresh)
        await run_email(send_team_order_update_email, fresh, "delivered")
    problem = "the customer refused the book" if code == wakilni.SUCCESS and status.get("rejected") else PROBLEM_STATUSES.get(code)
    alert_key = f"{code}:{label}"
    if problem and delivery.get("alerted") != alert_key:
        await db.orders.update_one({"id": order_id}, {"$set": {"delivery.alerted": alert_key}})
        fresh = await db.orders.find_one({"id": order_id}, {"_id": 0})
        await run_email(send_delivery_problem_email, fresh, f"{problem} (Wakilni: {label or code})")
    return await db.orders.find_one({"id": order_id}, {"_id": 0})


# Wakilni down for this long (every round failing): the admin hears about
# it, once. Shorter outages (an overloaded server…) just wait for the next
# round, without an alert each time.
OUTAGE_ALERT_AFTER_SECONDS = 3 * 3600


async def sync_all_deliveries() -> dict:
    """Every Wakilni delivery still on its way, followed (the scheduler's job)."""
    orders = await db.orders.find(
        {"delivery.delivery_id": {"$exists": True}, "status": {"$nin": ["delivered", "cancelled"]}},
        {"_id": 0, "id": 1},
    ).to_list(1000)
    checked, failed = 0, 0
    for o in orders:
        try:
            await sync_delivery(o["id"])
            checked += 1
        except wakilni.WakilniUnavailable as e:
            # Wakilni is down: the other deliveries would fail the same
            # way — they wait for the next round.
            failed += 1
            await _wakilni_down(o["id"], e)
            return {"checked": checked, "failed": failed, "wakilni_down": True}
        except Exception as e:
            failed += 1
            logger.error(f"Commande {o['id']} : suivi Wakilni impossible : {e}")
    if checked:
        await db.app_state.delete_one({"id": "wakilni_outage"})
    return {"checked": checked, "failed": failed}


async def _wakilni_down(order_id: str, error: Exception):
    now = datetime.now(timezone.utc)
    await db.app_state.update_one(
        {"id": "wakilni_outage"}, {"$setOnInsert": {"id": "wakilni_outage", "since": now.isoformat()}}, upsert=True
    )
    outage = await db.app_state.find_one({"id": "wakilni_outage"}, {"_id": 0})
    hours = (now - datetime.fromisoformat(outage["since"])).total_seconds() / 3600
    if hours * 3600 >= OUTAGE_ALERT_AFTER_SECONDS and not outage.get("alerted"):
        await db.app_state.update_one({"id": "wakilni_outage"}, {"$set": {"alerted": True}})
        logger.error(f"Wakilni injoignable depuis {hours:.0f} h : suivi des livraisons en attente ({error})")
    else:
        logger.warning(f"Commande {order_id} : Wakilni indisponible, nouvel essai au prochain passage : {error}")


async def cancel_delivery(order_id: str, reason: str) -> dict:
    """Cancels the Wakilni delivery (only possible while Wakilni hasn't
    confirmed it); the order can then get a new one."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    delivery = (order or {}).get("delivery") or {}
    if not delivery.get("delivery_id"):
        return order or {}
    await run_blocking(wakilni.cancel_delivery, delivery["delivery_id"], reason)
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"delivery": {"provider": "wakilni", "cancelled": {**delivery, "at": _now(), "reason": reason}}}},
    )
    return await db.orders.find_one({"id": order_id}, {"_id": 0})
