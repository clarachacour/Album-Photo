"""Customer order routes and the signed printer links."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from pymongo.errors import DuplicateKeyError

from app.config import R2_BUCKET_NAME
from app.core.auth import get_current_user
from app.core.signed_links import verify_order_action
from app.db import db
from app.schemas import OrderCreate, OrderFeedbackInput
from app.services.email import send_delivery_pickup_email, send_order_confirmation_email
from app.services.orders import (
    ORDER_STATUS_LABELS,
    ORDER_STATUS_SEQUENCE,
    start_order_pdf_generation,
)
from app.services.pricing import billed_page_count, compute_order_price_cents
from app.services.storage import get_r2_client

router = APIRouter()


@router.post("/orders")
async def create_order(data: OrderCreate, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    album = await db.albums.find_one({"id": data.album_id, "user_id": user["id"]})
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    if not album.get("pages"):
        raise HTTPException(status_code=400, detail="This album has no pages yet")
    # Nothing previously stopped a second order for the same album — and
    # since this whole endpoint is awaited synchronously (generation can
    # run for hours; see the comment on generate_order_pdf below for why
    # that's deliberate), a customer who re-opened the checkout page while
    # their first order's request was still silently pending — a second
    # tab, the back button, a reload — could place a genuine duplicate
    # with nothing telling them the first one had already gone through.
    # reject_if_ordered already stops them from editing the album at that
    # point; this stops the same root cause from also producing two paid
    # orders for one book.
    existing_order = await db.orders.find_one({"album_id": data.album_id})
    if existing_order:
        raise HTTPException(status_code=409, detail="An order already exists for this album")
    unit_price = compute_order_price_cents(album.get("size", "A4"), billed_page_count(album))
    order_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    order_doc = {
        "id": order_id,
        "user_id": user["id"],
        "album_id": album["id"],
        "album_title": album.get("title", "Album"),
        "size": album.get("size", "A4"),
        "orientation": album.get("orientation", "portrait"),
        "quantity": data.quantity,
        "unit_price_cents": unit_price,
        "total_price_cents": unit_price * data.quantity,
        "currency": "usd",
        "shipping_address": data.shipping_address.dict(),
        "status": "pending_payment",
        "status_history": [{"status": "pending_payment", "at": now}],
        "pdf_ready": False,
        "pdf_path": None,
        "tracking_number": None,
        "created_at": now,
        "updated_at": now,
    }
    try:
        await db.orders.insert_one(order_doc)
    except DuplicateKeyError:
        # A second checkout request for the same album got here at the same
        # time: the unique index on orders.album_id keeps only the first.
        raise HTTPException(status_code=409, detail="An order already exists for this album")
    # Sent right here, before generation even starts — not once the PDF is
    # ready (which used to be the trigger, tucked inside
    # generate_order_pdf's "printing" transition). Generation alone can
    # take anywhere from minutes to a couple of hours (see the 100-page
    # test album), and the customer shouldn't be left wondering whether
    # their order even went through for that whole stretch. The email's
    # own wording already fits this ("we've received it and will start
    # preparing your book" — never claims the PDF is done), so only the
    # trigger moved, not the text.
    send_order_confirmation_email(user.get("email"), user.get("name"), order_doc)
    # Through the Cloud Tasks queue when configured: the customer gets
    # their answer at once and a failed generation is retried (background
    # work inside this request doesn't survive on Cloud Run). Without the
    # queue, generated here while the request waits, as before.
    await start_order_pdf_generation(order_doc)
    fresh_order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return fresh_order or order_doc

@router.get("/order-actions/{order_id}/download")
async def order_action_download_pdf(order_id: str, token: str = Query(None)):
    """The printer's download link — no login, just the signed token
    mailed to them alongside it (see send_printer_order_email). A
    presigned R2 URL rather than proxying the bytes here, same reasoning
    as admin_download_order_pdf: a print-quality album PDF can easily
    exceed Cloud Run's own response-size ceiling on this backend, well
    separate from the render-time chunking concern."""
    if not verify_order_action(order_id, "download", token):
        raise HTTPException(status_code=403, detail="Invalid or expired link")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order or not order.get("pdf_path"):
        raise HTTPException(status_code=404, detail="No PDF found for this order")
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

@router.get("/order-actions/{order_id}/ready")
async def order_action_mark_ready(order_id: str, token: str = Query(None)):
    """The printer's "ready for delivery" link — moves the order to
    ready_for_delivery and, right then, notifies the delivery company
    (see send_delivery_pickup_email). Returns a plain confirmation page
    since a person at the print shop is the one clicking this in their
    browser, not calling it as an API."""
    if not verify_order_action(order_id, "ready", token):
        raise HTTPException(status_code=403, detail="Invalid or expired link")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] != "ready_for_delivery":
        now = datetime.now(timezone.utc).isoformat()
        await db.orders.update_one(
            {"id": order_id},
            {"$set": {"status": "ready_for_delivery", "updated_at": now}, "$push": {"status_history": {"status": "ready_for_delivery", "at": now}}},
        )
        order["status"] = "ready_for_delivery"
        send_delivery_pickup_email(order)
    return HTMLResponse("<html><body style='font-family:sans-serif; text-align:center; padding:60px;'>"
                         "<h2>Thanks — the delivery company has been notified.</h2></body></html>")

@router.get("/orders")
async def list_orders(user: dict = Depends(get_current_user)):
    orders = await db.orders.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return orders

@router.get("/orders/{order_id}")
async def get_order(order_id: str, user: dict = Depends(get_current_user)):
    order = await db.orders.find_one({"id": order_id, "user_id": user["id"]}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] == "cancelled":
        timeline = [{"status": "cancelled", "label": ORDER_STATUS_LABELS["cancelled"], "done": True}]
    else:
        current_idx = ORDER_STATUS_SEQUENCE.index(order["status"]) if order["status"] in ORDER_STATUS_SEQUENCE else 0
        timeline = [
            {"status": s, "label": ORDER_STATUS_LABELS[s], "done": i <= current_idx}
            for i, s in enumerate(ORDER_STATUS_SEQUENCE)
        ]
    order["timeline"] = timeline
    order["status_label"] = ORDER_STATUS_LABELS.get(order["status"], order["status"])
    return order

@router.post("/orders/{order_id}/feedback")
async def submit_order_feedback(order_id: str, data: OrderFeedbackInput, user: dict = Depends(get_current_user)):
    """A simple comment about how a specific order turned out — distinct
    on purpose from /contact, which is for something going wrong and
    needing a reply. This is one-way (no response expected, nothing here
    notifies support) and tied to one order, not a general inbox message.
    Stored directly on the order document rather than a separate
    collection — there's only ever one feedback per order, so no need for
    a whole collection just to look it up by order_id."""
    order = await db.orders.find_one({"id": order_id, "user_id": user["id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"feedback": {"comment": data.comment, "submitted_at": datetime.now(timezone.utc).isoformat()}}},
    )
    return {"message": "Thanks for your feedback!"}
