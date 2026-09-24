"""Admin-only order management."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.config import R2_BUCKET_NAME
from app.core.auth import decode_token, get_current_user, require_admin
from app.db import db
from app.schemas import OrderStatusUpdate
from app.services.email import (
    send_order_delivered_feedback_email,
    send_order_shipped_email,
    send_printer_order_email,
)
from app.services.orders import (
    ORDER_STATUSES,
    generate_order_pdf,
    purge_stale_pdf_generation_slots,
)
from app.services.storage import get_r2_client

router = APIRouter()


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
    for o in orders:
        o["pdf_generating"] = o["id"] in active_slot_order_ids
    return orders

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
        raise HTTPException(status_code=404, detail="Commande introuvable")
    if not order.get("pdf_path"):
        raise HTTPException(status_code=404, detail="Le PDF de cette commande n'est pas encore prêt")
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
    """Re-runs the exact same PDF generation generate_order_pdf already
    does for a brand-new order — for the day generation fails (memory
    limit, a stuck browser render, anything transient) and needs a retry.
    Awaited directly rather than dispatched as a background task — see
    create_order's comment on why: tried twice, failed silently both
    times even with instance-based billing and min-instances=1 in place.
    A slower response that reliably finishes beats a fast one that might
    not."""
    require_admin(user)
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")
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
    await generate_order_pdf(order_id, order["album_id"], order["user_id"])
    fresh = await db.orders.find_one({"id": order_id}, {"_id": 0})
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
        raise HTTPException(status_code=404, detail="Commande introuvable")
    if not order.get("pdf_ready") or not order.get("pdf_path"):
        raise HTTPException(status_code=400, detail="Le PDF de cette commande n'est pas encore prêt — régénérez-le d'abord")
    send_printer_order_email(order)
    return {"sent": True}

# Which customer email (if any) fires automatically when an order moves
# INTO a given status — keeps "every status change tells the customer
# what's going on" as one small table instead of scattered if/elif
# branches that are easy to miss updating when a new status is added.
STATUS_CUSTOMER_EMAIL = {
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
        raise HTTPException(status_code=404, detail="Commande introuvable")
    now = datetime.now(timezone.utc).isoformat()
    update = {"status": data.status, "updated_at": now}
    if data.tracking_number is not None:
        update["tracking_number"] = data.tracking_number
    await db.orders.update_one(
        {"id": order_id},
        {"$set": update, "$push": {"status_history": {"status": data.status, "at": now}}},
    )
    fresh = await db.orders.find_one({"id": order_id}, {"_id": 0})
    email_fn = STATUS_CUSTOMER_EMAIL.get(data.status)
    if email_fn:
        customer = await db.users.find_one({"id": order["user_id"]}, {"_id": 0})
        if customer:
            email_fn(customer.get("email"), customer.get("name"), fresh)
    return fresh
