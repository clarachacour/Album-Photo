"""WhatsApp messages to Wakilni's team, through Meta's Cloud API: a new
pickup at the printer, with Wakilni's order number (see dispatch_delivery
in services/delivery.py).

WhatsApp only lets a business start a conversation with a template Meta
has approved, so the text lives in Meta's WhatsApp Manager
(WHATSAPP_PICKUP_TEMPLATE); only its variables are sent from here.

Blocking calls (requests): run them in a thread (run_blocking).
"""
import logging
import re

import requests

from app.config import (
    WHATSAPP_API_VERSION,
    WHATSAPP_PHONE_NUMBER_ID,
    WHATSAPP_PICKUP_TEMPLATE,
    WHATSAPP_PICKUP_TO,
    WHATSAPP_TEMPLATE_LANGUAGE,
    WHATSAPP_TOKEN,
)

logger = logging.getLogger(__name__)

TIMEOUT = 15


class WhatsAppError(Exception):
    pass


def configured() -> bool:
    return bool(WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_PICKUP_TO)


def _number(value: str) -> str:
    """Digits only, with the country code, as the API wants it (961…)."""
    digits = re.sub(r"\D", "", value)
    return digits[2:] if digits.startswith("00") else digits


def _send_template(to: str, params: list):
    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    body = {
        "messaging_product": "whatsapp",
        "to": _number(to),
        "type": "template",
        "template": {
            "name": WHATSAPP_PICKUP_TEMPLATE,
            "language": {"code": WHATSAPP_TEMPLATE_LANGUAGE},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": str(p)} for p in params]}],
        },
    }
    try:
        res = requests.post(url, json=body, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise WhatsAppError(str(e)) from e
    if res.status_code >= 300:
        try:
            message = res.json().get("error", {}).get("message") or res.text
        except ValueError:
            message = res.text
        raise WhatsAppError(f"{res.status_code}: {message}"[:300])


def send_pickup(delivery_id, albums: int) -> list:
    """Tells each of Wakilni's people about a new pickup at the printer.
    Returns the numbers it couldn't reach (empty when all went through)."""
    failed = []
    for to in WHATSAPP_PICKUP_TO:
        try:
            _send_template(to, [delivery_id, albums])
        except WhatsAppError as e:
            logger.error(f"WhatsApp à {to} (pickup Wakilni {delivery_id}) non envoyé : {e}")
            failed.append(f"{to} ({e})")
    return failed
