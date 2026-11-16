"""Whish Pay: the payment link where a customer pays with the Whish app
(QR code or six-digit code), and the payment's status.

The API (whish-partners.pages.dev, Whish Pay v2): every call carries the
channel, secret and websiteUrl Whish issued; every answer is HTTP 200 with
{"status", "code", "data"} — status true: done; false with code "500":
no outcome yet (pending); false with another code: refused.
The keys live on Cloud Run (config.WHISH_*), never in the code or logs."""
import logging

import requests

from app import config

logger = logging.getLogger(__name__)

BASE_URLS = {
    "sandbox": "https://partner.api.sbx.whish.money/itel-service/api",
    "production": "https://api.whish.money/itel-service/api",
}
# Who calls, as Whish asks (app/version, site, contact).
USER_AGENT = "Everbook/1.0 (https://everbook-album.com; orders@everbook-album.com)"


class WhishError(Exception):
    """Whish refused the call (code: its error code) or couldn't be reached."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


def enabled() -> bool:
    return bool(config.WHISH_CHANNEL and config.WHISH_SECRET and config.WHISH_WEBSITE_URL)


def _base_url() -> str:
    return BASE_URLS["production" if config.WHISH_ENV == "production" else "sandbox"]


def _call(path: str, body: dict) -> dict:
    """POSTs to Whish and returns `data`; WhishError otherwise ("pending"
    for a call whose outcome isn't known yet, code 500)."""
    headers = {
        "channel": config.WHISH_CHANNEL or "",
        "secret": config.WHISH_SECRET or "",
        "websiteUrl": config.WHISH_WEBSITE_URL or "",
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(_base_url() + path, json=body, headers=headers, timeout=20)
        payload = resp.json()
    except Exception as e:
        raise WhishError("unreachable", str(e)[:200]) from None
    if payload.get("status") is True:
        return payload.get("data") or {}
    code = str(payload.get("code") or "unknown")
    message = ((payload.get("dialog") or {}).get("message") or "") if isinstance(payload.get("dialog"), dict) else ""
    raise WhishError("pending" if code == "500" else code, message)


def create_payment(*, amount_cents: int, external_id: str, invoice: str, success_callback: str,
                   failure_callback: str, success_redirect: str, failure_redirect: str) -> str:
    """A payment link (collectUrl) for this amount in US dollars. The same
    external_id sent again gives back the same link (Whish never charges it
    twice)."""
    data = _call("/payment/whish", {
        "amount": f"{amount_cents / 100:.2f}",
        "currency": "USD",
        "invoice": invoice[:200],
        "externalId": external_id,
        "successCallbackUrl": success_callback,
        "failureCallbackUrl": failure_callback,
        "successRedirectUrl": success_redirect,
        "failureRedirectUrl": failure_redirect,
    })
    url = data.get("collectUrl")
    if not url:
        raise WhishError("no_link", "Whish gave no payment link")
    return url


def payment_status(external_id: str) -> str:
    """"success" (paid), "pending" (not yet, also after a failed try),
    "failed" (expired unpaid), "refunded", or "unknown"."""
    data = _call("/payment/collect/status", {"currency": "USD", "externalId": external_id})
    return str(data.get("collectStatus") or "unknown")
