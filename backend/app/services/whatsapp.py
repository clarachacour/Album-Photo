"""WhatsApp messages through Meta's Cloud API, from Everbook's WhatsApp
Business number:
- to Wakilni's team: a new pickup at the printer, with Wakilni's order
  number (see dispatch_delivery in services/delivery.py);
- to Bookstop's team: a new order to print (see flush_printer_queue in
  services/print_groups.py).

WhatsApp only lets a business start a conversation with a template Meta
has approved, so the texts live in Meta's WhatsApp Manager
(WHATSAPP_PICKUP_TEMPLATE, WHATSAPP_PRINTER_TEMPLATE); only their
variables are sent from here.

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
    WHATSAPP_PRINTER_TEMPLATE,
    WHATSAPP_PRINTER_TO,
    WHATSAPP_TEMPLATE_LANGUAGE,
    WHATSAPP_TOKEN,
)

logger = logging.getLogger(__name__)

TIMEOUT = 15


class WhatsAppError(Exception):
    pass


def configured(audience: str = "pickup") -> bool:
    """Whether messages can go out: to Wakilni's team ("pickup") or to
    Bookstop's ("printer")."""
    recipients = WHATSAPP_PRINTER_TO if audience == "printer" else WHATSAPP_PICKUP_TO
    return bool(WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID and recipients)


def _number(value: str) -> str:
    """Digits only, with the country code, as the API wants it (961…)."""
    digits = re.sub(r"\D", "", value)
    return digits[2:] if digits.startswith("00") else digits


def _send_template(to: str, template: str, params: list):
    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    body = {
        "messaging_product": "whatsapp",
        "to": _number(to),
        "type": "template",
        "template": {
            "name": template,
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


def _send_to_all(recipients: list, template: str, params: list, about: str) -> list:
    """Sends the template to each number. Returns the numbers it couldn't
    reach (empty when all went through)."""
    failed = []
    for to in recipients:
        try:
            _send_template(to, template, params)
        except WhatsAppError as e:
            logger.error(f"WhatsApp à {to} ({about}) non envoyé : {e}")
            failed.append(f"{to} ({e})")
    return failed


def send_pickup(delivery_id, albums: int) -> list:
    """Tells Wakilni's team about a new pickup at the printer."""
    return _send_to_all(WHATSAPP_PICKUP_TO, WHATSAPP_PICKUP_TEMPLATE, [delivery_id, albums], f"pickup Wakilni {delivery_id}")


def send_print_order(numbers: str, albums: int) -> list:
    """Tells Bookstop's team about a new order to print."""
    return _send_to_all(WHATSAPP_PRINTER_TO, WHATSAPP_PRINTER_TEMPLATE, [numbers, albums], f"commande {numbers} à imprimer")
