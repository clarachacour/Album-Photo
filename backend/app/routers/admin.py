"""Admin-only order management."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import RedirectResponse, Response

from app.config import R2_BUCKET_NAME
from app.core.auth import decode_token, get_current_user, require_admin
from app.db import db
from app.monitoring import send_test_error
from app.schemas import OrderStatusUpdate, ShippingAddress
from app.services.email import (
    send_order_delivered_feedback_email,
    send_order_shipped_email,
    send_order_in_production_email,
    send_printer_order_email,
    send_team_order_update_email,
)
from app.services.orders import (
    ORDER_STATUSES,
    deliver_digital_if_ready,
    order_kind,
    purge_stale_pdf_generation_slots,
    start_order_pdf_generation,
    status_sequence,
)
from app.services import delivery as deliveries
from app.services.print_groups import flush_printer_queue, group_of
from app.services import wakilni
from app.services import printer_statement
from app.config import BACKEND_URL
from app.services.storage import get_r2_client
from app.core.executors import run_blocking, run_email

router = APIRouter()


@router.post("/admin/sentry-test")
async def admin_sentry_test(user: dict = Depends(get_current_user)):
    """Checks the backend is connected to Sentry."""
    require_admin(user)
    event_id = send_test_error()
    return {"configured": event_id is not None, "event_id": event_id}


@router.get("/admin/orders")
async def admin_list_orders(user: dict = Depends(get_current_user)):
    """Every order across every customer, newest first — the shipping
    name/address/phone and which album (title, id) are what you need to
    know who a given order.pdf in R2 (orders/{order_id}.pdf) actually
    belongs to and where it ships. Not scoped to user_id the way the
    customer-facing /orders is — that's exactly the point of this one."""
    require_admin(user)
    orders = await db.orders.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    # pdf_ready=False on its own is ambiguous — it's the same whether a
    # generation is actively rendering right now, genuinely failed, or
    # (rare) an instance was killed outright (e.g. an OOM kill from Cloud
    # Run) before it ever reached the except/pdf_error assignment. The
    # pdf_generation_slots collection has a live row for exactly the
    # order(s) currently holding a generation slot, so cross-referencing
    # it here lets the admin UI show "generating" instead of a flat
    # "failed" for an order that's simply still running. Purge stale slots
    # first (see purge_stale_pdf_generation_slots) — otherwise a slot
    # orphaned by a hard Cloud Run timeout would show "Generating…" here
    # indefinitely, with nothing to ever clear it.
    await purge_stale_pdf_generation_slots()
    active_slot_order_ids = {
        s["order_id"] async for s in db.pdf_generation_slots.find({}, {"order_id": 1})
    }
    # Also "generating" while waiting in the Cloud Tasks queue (between
    # attempts included), until the PDF is ready or the last attempt failed.
    queue_cutoff = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    for o in orders:
        queued = bool(o.get("pdf_queued_at")) and o["pdf_queued_at"] > queue_cutoff and not o.get("pdf_ready")
        o["pdf_generating"] = o["id"] in active_slot_order_ids or queued
    # Who ordered it: a digital album has no delivery address to tell.
    users = {
        u["id"]: u
        async for u in db.users.find({"id": {"$in": list({o["user_id"] for o in orders if o.get("user_id")})}}, {"_id": 0, "id": 1, "name": 1, "email": 1})
    }
    for o in orders:
        customer = users.get(o.get("user_id")) or {}
        o["customer"] = {"name": customer.get("name"), "email": customer.get("email")}
    # The PDF is made once, from the album as it was then: an album edited
    # afterwards (the admin fixing it before printing) needs its PDF made
    # again, or the printer gets the old one.
    edited = {
        a["id"]: a.get("updated_at")
        async for a in db.albums.find({"id": {"$in": list({o["album_id"] for o in orders if o.get("album_id")})}}, {"_id": 0, "id": 1, "updated_at": 1})
    }
    for o in orders:
        made_at = pdf_made_at(o)
        album_edited_at = edited.get(o.get("album_id"))
        o["album_changed_since_pdf"] = bool(o.get("pdf_ready") and made_at and album_edited_at and album_edited_at > made_at)
    return orders


def pdf_made_at(order: dict) -> str | None:
    """When the order's PDF was made. Orders from before pdf_generated_at
    was kept: the PDF went with the move to "printing"."""
    if order.get("pdf_generated_at"):
        return order["pdf_generated_at"]
    printing = [h["at"] for h in order.get("status_history") or [] if h.get("status") == "printing"]
    return printing[-1] if printing else None

@router.get("/admin/orders/{order_id}/pdf")
async def admin_download_order_pdf(order_id: str, auth: str = Query(None), authorization: str = Header(None)):
    """Redirects straight to a short-lived, signed R2 URL rather than
    proxying the file's bytes through this backend and back out again —
    a print-quality album PDF easily runs past 100MB (24 pages, up to 4
    photos each, was 110MB), and Cloud Run enforces its own hard cap on
    how large a single HTTP response through the normal request/response
    path can be, well under that ("Response size was too large") — a
    completely different ceiling from the render-time V8 string-length
    one chunking exists for.

    Accepts the auth token via query param (same pattern as
    get_photo_image) in addition to the header, and the frontend now
    navigates the browser straight to this URL rather than fetching it
    through axios — a plain top-level navigation follows the redirect to
    R2 with no CORS involved at all, where an XHR/fetch-based request
    (axios's responseType: "blob", tried first) does still apply CORS to
    the redirect's target, and the R2 bucket has no CORS policy allowing
    this frontend's origin — the fetch was being silently blocked by the
    browser, which is why downloads kept failing with a "not ready yet"
    message despite the redirect itself working (that message is really
    just this endpoint's generic error fallback, not a sign the PDF
    itself was ever actually missing)."""
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    elif auth:
        token = auth
    user_id = decode_token(token) if token else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    require_admin(user)
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.get("pdf_path"):
        raise HTTPException(status_code=404, detail="This order's PDF is not ready yet")
    url = get_r2_client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": R2_BUCKET_NAME,
            "Key": order["pdf_path"],
            "ResponseContentDisposition": f'attachment; filename="{order_id}.pdf"',
            "ResponseContentType": "application/pdf",
        },
        ExpiresIn=3600,
    )
    return RedirectResponse(url)

@router.post("/admin/orders/{order_id}/regenerate-pdf")
async def admin_regenerate_order_pdf(order_id: str, user: dict = Depends(get_current_user)):
    """Re-runs the order's PDF generation (after a failure, or after a
    fix): through the Cloud Tasks queue when configured, returning at
    once, otherwise here while the request waits."""
    require_admin(user)
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    # The frontend already hides the regenerate button while pdf_generating
    # is true, but that's a UI nicety, not a guarantee — a stale page, a
    # second tab, or a direct API call all bypass it. This is the check
    # that actually matters: refuse outright rather than letting a second
    # generate_order_pdf run concurrently for the same order_id, which
    # would just have the second call sit blocked in
    # _acquire_pdf_generation_slot behind the first for no benefit. Purged
    # first so a slot orphaned by a hard Cloud Run timeout (see
    # purge_stale_pdf_generation_slots) can't itself be the reason this
    # 409s — without it, a genuinely dead generation would block every
    # future regenerate attempt on this order forever, not just the live
    # one it was guarding against.
    await purge_stale_pdf_generation_slots()
    if await db.pdf_generation_slots.find_one({"order_id": order_id}):
        raise HTTPException(status_code=409, detail="A generation is already in progress for this order")
    await db.orders.update_one({"id": order_id}, {"$set": {"pdf_ready": False, "pdf_path": None, "pdf_error": None}})
    queued = await start_order_pdf_generation(order)
    fresh = await db.orders.find_one({"id": order_id}, {"_id": 0})
    fresh["pdf_queued"] = queued
    return fresh

@router.post("/admin/orders/{order_id}/resend-printer-email")
async def admin_resend_printer_email(order_id: str, user: dict = Depends(get_current_user)):
    """Re-sends the printer notification email for an order whose PDF is
    already generated — for exactly the situation that comes up while
    still testing/fixing email delivery (a wrong BACKEND_URL, SMTP not
    yet configured, etc.): the PDF itself is already correct and doesn't
    need regenerating, only the email carrying its download link does.
    Refuses if there's no PDF yet — regenerate the PDF first in that
    case, which sends this same email itself once generation succeeds."""
    require_admin(user)
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order_kind(order) == "digital":
        raise HTTPException(status_code=400, detail="A digital album isn't printed: there's no printer email")
    if not order.get("pdf_ready") or not order.get("pdf_path"):
        raise HTTPException(status_code=400, detail="This order's PDF is not ready yet — regenerate it first")
    if order.get("printer_pending_at"):
        # Still waiting to be grouped: sent now, with whatever is grouped.
        await flush_printer_queue(force_order_id=order_id)
    else:
        group = await group_of(order)
        await run_email(send_printer_order_email, group[0], group)
    return {"sent": True}

# Which customer email (if any) fires automatically when an order moves
# INTO a given status — keeps "every status change tells the customer
# what's going on" as one small table instead of scattered if/elif
# branches that are easy to miss updating when a new status is added.
STATUS_CUSTOMER_EMAIL = {
    "printing": send_order_in_production_email,
    "shipped": send_order_shipped_email,
    "delivered": send_order_delivered_feedback_email,
}

@router.patch("/admin/orders/{order_id}/status")
async def admin_update_order_status(order_id: str, data: OrderStatusUpdate, user: dict = Depends(get_current_user)):
    """Manual status moves the printer/delivery workflow doesn't cover on
    its own — mainly marking an order "shipped" (with a tracking number)
    once the delivery company has actually handed it off, and "delivered"
    afterward. Whichever status this lands on, if it's one customers care
    about hearing (see STATUS_CUSTOMER_EMAIL), that email goes out right
    here — the same "every update tells the customer" guarantee the
    printer/delivery links already give the rest of the flow."""
    require_admin(user)
    if data.status not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail=f"Statut inconnu : {data.status}")
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if data.status != "cancelled" and data.status not in status_sequence(order):
        raise HTTPException(status_code=400, detail=f"Statut « {data.status} » impossible pour ce type de commande")
    now = datetime.now(timezone.utc).isoformat()
    update = {"status": data.status, "updated_at": now}
    if data.tracking_number is not None:
        update["tracking_number"] = data.tracking_number
    await db.orders.update_one(
        {"id": order_id},
        {"$set": update, "$push": {"status_history": {"status": data.status, "at": now}}},
    )
    if order_kind(order) == "digital" and data.status in ("paid", "available"):
        # Paid: the customer gets their PDF now (or the moment it's made).
        await deliver_digital_if_ready(order_id)
        return await db.orders.find_one({"id": order_id}, {"_id": 0})
    fresh = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if data.status == "delivered" and order.get("status") != "delivered":
        await run_email(send_team_order_update_email, fresh, "delivered")
    email_fn = STATUS_CUSTOMER_EMAIL.get(data.status)
    if email_fn:
        customer = await db.users.find_one({"id": order["user_id"]}, {"_id": 0})
        if customer:
            await run_email(email_fn, customer.get("email"), customer.get("name"), fresh)
    return fresh


@router.patch("/admin/orders/{order_id}/shipping-address")
async def admin_update_shipping_address(order_id: str, data: ShippingAddress, user: dict = Depends(get_current_user)):
    """Corrects a printed order's delivery address (a wrong address typed by
    the customer). Refused once a Wakilni delivery exists for it: cancel that
    delivery first (it carries the old address), then a new one is created
    with the corrected address."""
    require_admin(user)
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order_kind(order) != "print":
        raise HTTPException(status_code=400, detail="A digital album has no delivery address")
    if (order.get("delivery") or {}).get("delivery_id"):
        raise HTTPException(status_code=409, detail="A Wakilni delivery already exists with the old address: cancel it first, then change the address")
    now = datetime.now(timezone.utc).isoformat()
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"shipping_address": data.dict(), "updated_at": now}, "$push": {"address_history": {"previous": order.get("shipping_address"), "at": now, "by": user.get("email")}}},
    )
    return await db.orders.find_one({"id": order_id}, {"_id": 0})


# ---------- Wakilni delivery, by hand ----------
async def _printed_order(order_id: str) -> dict:
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order_kind(order) != "print":
        raise HTTPException(status_code=400, detail="A digital album isn't delivered")
    if not wakilni.configured():
        raise HTTPException(status_code=400, detail="Wakilni isn't configured on this server (WAKILNI_KEY / WAKILNI_SECRET)")
    return order


@router.post("/admin/orders/{order_id}/delivery")
async def admin_create_delivery(order_id: str, user: dict = Depends(get_current_user)):
    """Creates the Wakilni delivery now (when the automatic one failed, or
    before the printer's click)."""
    require_admin(user)
    await _printed_order(order_id)
    order = await deliveries.dispatch_delivery(order_id)
    error = (order.get("delivery") or {}).get("error")
    if error and not (order.get("delivery") or {}).get("delivery_id"):
        raise HTTPException(status_code=502, detail=f"Wakilni: {error}")
    return order


@router.post("/admin/orders/{order_id}/delivery/refresh")
async def admin_refresh_delivery(order_id: str, user: dict = Depends(get_current_user)):
    require_admin(user)
    await _printed_order(order_id)
    try:
        return await deliveries.sync_delivery(order_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Wakilni: {e}")


@router.get("/admin/orders/{order_id}/delivery/history")
async def admin_delivery_history(order_id: str, user: dict = Depends(get_current_user)):
    """The Wakilni delivery's full history: every step and the courier's comments."""
    require_admin(user)
    order = await _printed_order(order_id)
    delivery_id = (order.get("delivery") or {}).get("delivery_id")
    if not delivery_id:
        raise HTTPException(status_code=404, detail="No Wakilni delivery for this order")
    try:
        return await run_blocking(wakilni.delivery_history, delivery_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Wakilni: {e}")


@router.post("/admin/orders/{order_id}/delivery/cancel")
async def admin_cancel_delivery(order_id: str, user: dict = Depends(get_current_user)):
    """Cancels the Wakilni delivery (possible only while still pending there)."""
    require_admin(user)
    await _printed_order(order_id)
    try:
        return await deliveries.cancel_delivery(order_id, "Cancelled by Everbook")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Wakilni: {e}")


async def _admin_from_query_or_header(auth: str = None, authorization: str = None) -> dict:
    """The admin, from a Bearer header or an ?auth= token (a file the
    browser downloads by opening the link)."""
    token = authorization.split(" ", 1)[1] if authorization and authorization.lower().startswith("bearer ") else auth
    user_id = decode_token(token) if token else None
    user = await db.users.find_one({"id": user_id}, {"_id": 0}) if user_id else None
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    require_admin(user)
    return user


async def _statement_file() -> Response:
    orders = await db.orders.find({"kind": {"$ne": "digital"}}, {"_id": 0}).to_list(10000)
    missing = list({o["album_id"] for o in orders if o.get("album_id") and not o.get("page_count")})
    page_counts = {}
    if missing:
        async for a in db.albums.find({"id": {"$in": missing}}, {"_id": 0, "id": 1, "pages": 1}):
            page_counts[a["id"]] = len(a.get("pages") or [])
    data = printer_statement.build_statement_xlsx(printer_statement.statement_rows(orders, page_counts))
    name = f"everbook-printer-statement-{datetime.now(timezone.utc):%Y-%m-%d}.xlsx"
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )


@router.get("/admin/printer-statement.xlsx")
async def admin_printer_statement(auth: str = Query(None), authorization: str = Header(None)):
    """The printer's statement as Excel, made now from the orders."""
    await _admin_from_query_or_header(auth, authorization)
    return await _statement_file()


@router.get("/admin/printer-statement-link")
async def admin_printer_statement_link(user: dict = Depends(get_current_user)):
    """The fixed link to send the printer once (WhatsApp): it always
    downloads the statement as it is that day. No customer price or
    details in it."""
    require_admin(user)
    return {"url": f"{BACKEND_URL}/api/printer-statement.xlsx?key={printer_statement.statement_key()}"}


@router.get("/printer-statement.xlsx")
async def printer_statement_for_printer(key: str = Query(None)):
    if not printer_statement.valid_statement_key(key):
        raise HTTPException(status_code=403, detail="Invalid link")
    return await _statement_file()


@router.patch("/admin/orders/{order_id}/printer-payment")
async def admin_set_printer_payment(order_id: str, body: dict, user: dict = Depends(get_current_user)):
    """Marks an order paid to the printer (or not), with today's date."""
    require_admin(user)
    paid = bool(body.get("paid"))
    value = datetime.now(timezone.utc).isoformat() if paid else None
    res = await db.orders.update_one({"id": order_id}, {"$set": {"printer_paid_at": value}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"printer_paid_at": value}
