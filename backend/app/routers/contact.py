"""Contact form."""
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.core.rate_limit import CONTACT_LIMIT_PER_IP, rate_limiter
from app.core.security import client_ip
from app.db import db
from app.schemas import ContactInput
from app.services.email import send_email

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
        send_email(
            support_email,
            f"[Contact] {data.subject}",
            f"From: {data.name} <{data.email}>\n\n{data.message}",
        )
    return {"message": "Message envoyé, nous vous répondrons rapidement."}
