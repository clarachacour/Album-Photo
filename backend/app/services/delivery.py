"""Getting a printed book to its customer: a Wakilni delivery created when
the printer marks the book ready, then followed until it's delivered (see
services/wakilni.py). Without Wakilni configured, the courier gets an
email instead, as before."""
import logging
from datetime import datetime, timezone

from app.core.executors import run_blocking, run_email
from app.core.order_number import order_number
from app.db import db
from app.services import wakilni, whatsapp
from app.services.print_groups import group_of
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
    courier is emailed too and the admin is told. Albums ordered together
    (see services/print_groups.py) get one delivery between them. Returns
    the order."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        return {}
    group = await group_of(order)
    lead = group[0]
    ids = [o["id"] for o in group]
    if not wakilni.configured():
        await run_email(send_delivery_pickup_email, lead, group)
        return order
    existing = next(((o.get("delivery") or {}) for o in group if (o.get("delivery") or {}).get("delivery_id")), None)
    if existing:
        # Already created (for the group): every album of it follows it.
        await db.orders.update_many({"id": {"$in": ids}, "delivery.delivery_id": {"$exists": False}}, {"$set": {"delivery": existing, "tracking_number": existing.get("tracking_id")}})
        return await db.orders.find_one({"id": order_id}, {"_id": 0})
    try:
        created = await run_blocking(wakilni.create_delivery, group if len(group) > 1 else lead, await _customer(lead))
    except Exception as e:
        logger.error(f"Commande {lead['id']} : livraison Wakilni non créée : {e}")
        await db.orders.update_many({"id": {"$in": ids}}, {"$set": {"delivery": {"provider": "wakilni", "error": str(e)[:500], "at": _now()}}})
        lead = await db.orders.find_one({"id": lead["id"]}, {"_id": 0})
        await run_email(send_delivery_problem_email, lead, f"the Wakilni delivery couldn't be created ({str(e)[:200]})")
        await run_email(send_delivery_pickup_email, lead, group)  # the courier still hears about it
        return await db.orders.find_one({"id": order_id}, {"_id": 0})
    created.update(created_at=_now(), status_code=wakilni.PENDING, status_label="Pending")
    if len(group) > 1:
        created["order_ids"] = ids
    await db.orders.update_many({"id": {"$in": ids}}, {"$set": {"delivery": created, "tracking_number": created.get("tracking_id")}})
    logger.info(f"Commande(s) {', '.join(ids)} : livraison Wakilni {created.get('delivery_id')} créée")
    await _tell_wakilni_on_whatsapp(created, group)
    return await db.orders.find_one({"id": order_id}, {"_id": 0})


async def _tell_wakilni_on_whatsapp(created: dict, group: list):
    """Wakilni's team hears on WhatsApp that a pickup is waiting at the
    printer, with its order number (once per delivery). If it can't be
    sent, the admin is told: Wakilni still has the order in its system."""
    if not whatsapp.configured():
        return
    albums = sum(int(o.get("quantity") or 1) for o in group)
    failed = await run_blocking(whatsapp.send_pickup, created.get("delivery_id"), albums)
    sent = {"delivery.whatsapp_at": _now()} if not failed else {"delivery.whatsapp_failed": failed}
    await db.orders.update_many({"delivery.delivery_id": created.get("delivery_id")}, {"$set": sent})
    if failed:
        lead = await db.orders.find_one({"id": group[0]["id"]}, {"_id": 0})
        await run_email(send_delivery_problem_email, lead,
                        f"the WhatsApp message to Wakilni about the pickup (n° {created.get('delivery_id')}) couldn't be sent to "
                        f"{'; '.join(failed)}. Wakilni has the order in its system; let them know if needed")


async def sync_delivery(order_id: str) -> dict:
    """Asks Wakilni where the delivery is and follows it on the order — and
    on the customer's other albums in the same package (albums ordered
    together share one delivery): on its way → shipped, delivered →
    delivered, one email to the customer for the whole package each time;
    a problem → the admin is emailed (once per status)."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    delivery = (order or {}).get("delivery") or {}
    if not delivery.get("delivery_id") or not wakilni.configured():
        return order or {}
    members = await db.orders.find(
        {"delivery.delivery_id": delivery["delivery_id"], "status": {"$ne": "cancelled"}}, {"_id": 0}
    ).to_list(50) or [order]
    members.sort(key=lambda o: (o["id"] != (o.get("print_group") or o["id"]), o.get("created_at") or ""))
    ids = [o["id"] for o in members]
    status = await run_blocking(wakilni.delivery_status, delivery["delivery_id"])
    code, label = status.get("code"), status.get("label") or ""
    await db.orders.update_many(
        {"id": {"$in": ids}},
        {"$set": {"delivery.status_code": code, "delivery.status_label": label, "delivery.checked_at": _now()}},
    )
    customer = await _customer(members[0])
    if code == wakilni.PROCESSING:
        moving = [o for o in members if o["status"] in ("pending_payment", "paid", "processing", "printing", "ready_for_delivery")]
        for o in moving:
            await _set_status(o["id"], "shipped")
        if moving:
            fresh = await _fresh(moving)
            await run_email(send_order_shipped_email, customer.get("email"), customer.get("name"), fresh[0], fresh)
    elif code == wakilni.SUCCESS and not status.get("rejected"):
        arrived = [o for o in members if o["status"] != "delivered"]
        for o in arrived:
            await _set_status(o["id"], "delivered")
        if arrived:
            fresh = await _fresh(arrived)
            await run_email(send_order_delivered_feedback_email, customer.get("email"), customer.get("name"), fresh[0], fresh)
            for o in fresh:
                await run_email(send_team_order_update_email, o, "delivered")
    if code == wakilni.CANCELED:
        # Cancelled at Wakilni (on their portal, e.g. the printer clicked
        # "ready" too early): the order lets go of it, so the printer's next
        # "ready" click creates a new delivery.
        await _let_go_of_delivery(delivery, "cancelled at Wakilni")
        fresh = await db.orders.find_one({"id": ids[0]}, {"_id": 0})
        await run_email(send_delivery_problem_email, fresh,
                        f"the delivery was cancelled at Wakilni (n° {delivery['delivery_id']}): it's no longer linked to the order — "
                        "a new one will be created when the printer marks the book ready again")
        return await db.orders.find_one({"id": order_id}, {"_id": 0})
    problem = "the customer refused the book" if code == wakilni.SUCCESS and status.get("rejected") else PROBLEM_STATUSES.get(code)
    alert_key = f"{code}:{label}"
    if problem and delivery.get("alerted") != alert_key:
        await db.orders.update_many({"id": {"$in": ids}}, {"$set": {"delivery.alerted": alert_key}})
        fresh = await db.orders.find_one({"id": ids[0]}, {"_id": 0})
        await run_email(send_delivery_problem_email, fresh, f"{problem} (Wakilni: {label or code})")
    return await db.orders.find_one({"id": order_id}, {"_id": 0})


async def _fresh(orders: list) -> list:
    """The orders as they are now, in the same order."""
    found = {o["id"]: o for o in await db.orders.find({"id": {"$in": [o["id"] for o in orders]}}, {"_id": 0}).to_list(50)}
    return [found[o["id"]] for o in orders if o["id"] in found]


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
    seen = set()
    for o in orders:
        if o["id"] in seen:
            continue  # followed with another album of its package
        try:
            synced = await sync_delivery(o["id"])
            # The other albums of the same delivery were followed with it.
            delivery_id = ((synced or {}).get("delivery") or {}).get("delivery_id")
            if delivery_id:
                seen.update(x["id"] for x in await db.orders.find({"delivery.delivery_id": delivery_id}, {"_id": 0, "id": 1}).to_list(50))
            checked += 1
        except wakilni.WakilniUnavailable as e:
            # Wakilni is down: the other deliveries would fail the same
            # way — they wait for the next round.
            failed += 1
            await _wakilni_down(o["id"], e)
            return {"checked": checked, "failed": failed, "wakilni_down": True}
        except Exception as e:
            failed += 1
            logger.error(f"Commande {order_number(o)} ({o['id']}) : suivi Wakilni impossible : {e}")
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
        logger.warning(f"Commande {order_number({'id': order_id})} ({order_id}) : Wakilni indisponible, nouvel essai au prochain passage : {error}")


async def cancel_delivery(order_id: str, reason: str) -> dict:
    """Cancels the Wakilni delivery; the order can then get a new one (the
    printer's next "ready" click). Already cancelled at Wakilni (on their
    portal): just let go of it here."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    delivery = (order or {}).get("delivery") or {}
    if not delivery.get("delivery_id"):
        return order or {}
    try:
        await run_blocking(wakilni.cancel_delivery, delivery["delivery_id"], reason)
    except wakilni.WakilniError:
        status = await run_blocking(wakilni.delivery_status, delivery["delivery_id"])
        if status.get("code") != wakilni.CANCELED:
            raise
        reason = f"{reason} (already cancelled at Wakilni)"
    await _let_go_of_delivery(delivery, reason)
    return await db.orders.find_one({"id": order_id}, {"_id": 0})


async def _let_go_of_delivery(delivery: dict, reason: str):
    """The delivery is cancelled: kept for the record, no longer the
    order's — every album of it (albums ordered together share it)."""
    await db.orders.update_many(
        {"delivery.delivery_id": delivery["delivery_id"]},
        {"$set": {"delivery": {"provider": "wakilni", "cancelled": {**delivery, "at": _now(), "reason": reason}}}},
    )
