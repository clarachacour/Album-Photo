"""Contact form."""
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.core.rate_limit import CONTACT_LIMIT_PER_IP, rate_limiter
from app.core.security import client_ip
from app.db import db
from app.schemas import ContactInput
from app.services.email import _h, send_email
from app.core.executors import run_email

router = APIRouter()


@router.post("/contact")
async def submit_contact(data: ContactInput, request: Request):
    await rate_limiter.check_all([
        ("contact:ip", client_ip(request), *CONTACT_LIMIT_PER_IP),
    ])
    contact_id = str(uuid.uuid4())
    doc = {
        "id": contact_id,
        "name": data.name,
        "email": data.email.lower(),
        "subject": data.subject,
        "message": data.message,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.contact_messages.insert_one(doc)
    # Notify the team inbox if one is configured; never fails the request if
    # email sending isn't set up (already logged by send_email in that case).
    support_email = os.environ.get("SUPPORT_EMAIL")
    if support_email:
        # The sender's address written out in full (not as <address>, which
        # some mail apps hide as if it were markup) and set as Reply-To, so
        # "Reply" answers the customer directly.
        body = (
            f"Name: {data.name}\n"
            f"Email: {data.email}\n"
            f"Subject: {data.subject}\n\n"
            f"{data.message}\n\n"
            f"— Reply to this email to answer {data.name} directly."
        )
        html_body = (
            f"<p><strong>Name:</strong> {_h(data.name)}<br>"
            f"<strong>Email:</strong> <a href=\"mailto:{_h(data.email)}\">{_h(data.email)}</a><br>"
            f"<strong>Subject:</strong> {_h(data.subject)}</p>"
            f"<p style=\"white-space:pre-wrap\">{_h(data.message)}</p>"
            f"<p style=\"color:#73716A;font-size:13px\">Reply to this email to answer {_h(data.name)} directly.</p>"
        )
        await run_email(
            send_email,
            support_email,
            f"[Contact] {data.subject}",
            body,
            html_body,
            data.email,
        )
    return {"message": "Message sent — we'll get back to you soon."}
