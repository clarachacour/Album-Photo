"""Card payment with Cybersource Unified Checkout (the gateway areeba gives
its merchants in Lebanon).

How a card payment goes:

1. capture_context(): the server asks Cybersource for a one-time "capture
   context" (a JWT) for the amount to pay. The browser loads Cybersource's
   own script with it and shows the card form — the card number is typed
   into Cybersource's frames, never into our page or our server.
2. The form gives the browser a "transient token" (a JWT standing for the
   card, valid 15 minutes), sent to us with the checkout.
3. authorize_and_capture(): the server charges that token, for the amount
   it computed itself (never one from the browser).

Every request is signed with the REST shared secret key (HTTP Signature,
HMAC-SHA256), made in the Business Center: Payment Configuration → Key
Management → REST – Shared Secret.

Without CYBERSOURCE_MERCHANT_ID / KEY_ID / SECRET_KEY, card payment is off
(configured() is False) and the site keeps "coming soon"."""
import base64
import hashlib
import hmac
import json
import logging
from email.utils import formatdate

import requests

from app.config import (
    CYBERSOURCE_CARD_NETWORKS,
    CYBERSOURCE_CLIENT_VERSION,
    CYBERSOURCE_HOST,
    CYBERSOURCE_KEY_ID,
    CYBERSOURCE_MERCHANT_ID,
    CYBERSOURCE_SECRET_KEY,
    CYBERSOURCE_TARGET_ORIGINS,
)

logger = logging.getLogger(__name__)

CURRENCY = "USD"
TIMEOUT_SECONDS = 30
CAPTURE_CONTEXT_PATH = "/up/v1/capture-contexts"
PAYMENTS_PATH = "/pts/v2/payments"


class GatewayError(Exception):
    """Cybersource couldn't be reached or answered with an error. `sent`:
    whether the request may have reached them (a payment that timed out
    may still have gone through)."""

    def __init__(self, message: str, sent: bool = False):
        super().__init__(message)
        self.sent = sent


def configured() -> bool:
    return bool(CYBERSOURCE_MERCHANT_ID and CYBERSOURCE_KEY_ID and CYBERSOURCE_SECRET_KEY)


def amount_text(cents: int) -> str:
    return f"{cents / 100:.2f}"


def signed_headers(method: str, path: str, body: bytes = b"", date: str = None) -> dict:
    """The headers of a request signed the Cybersource way (HTTP Signature
    with the shared secret): host, date, the request's target, the body's
    SHA-256 digest (POST), the merchant id — signed together."""
    headers = {
        "host": CYBERSOURCE_HOST,
        "date": date or formatdate(usegmt=True),
        "v-c-merchant-id": CYBERSOURCE_MERCHANT_ID,
    }
    names = ["host", "date", "request-target"]
    if method.upper() != "GET":
        headers["digest"] = "SHA-256=" + base64.b64encode(hashlib.sha256(body).digest()).decode()
        names.append("digest")
    names.append("v-c-merchant-id")
    lines = [f"request-target: {method.lower()} {path}" if n == "request-target" else f"{n}: {headers[n]}" for n in names]
    secret = base64.b64decode(CYBERSOURCE_SECRET_KEY)
    signature = base64.b64encode(hmac.new(secret, "\n".join(lines).encode(), hashlib.sha256).digest()).decode()
    headers["signature"] = (
        f'keyid="{CYBERSOURCE_KEY_ID}", algorithm="HmacSHA256", headers="{" ".join(names)}", signature="{signature}"'
    )
    return headers


def _post(path: str, payload: dict) -> requests.Response:
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = signed_headers("POST", path, body)
    headers["content-type"] = "application/json;charset=utf-8"
    try:
        return requests.post(f"https://{CYBERSOURCE_HOST}{path}", data=body, headers=headers, timeout=TIMEOUT_SECONDS)
    except requests.ConnectionError as exc:
        # Refused before anything was sent (DNS, connection): nothing charged.
        raise GatewayError(f"Cybersource unreachable: {exc}", sent=False) from exc
    except requests.RequestException as exc:
        # A timeout or a cut connection: the request may have been handled.
        raise GatewayError(f"Cybersource didn't answer: {exc}", sent=True) from exc


def capture_context(amount_cents: int, lang: str = "en") -> str:
    """A one-time capture context (JWT) for paying amount_cents by card."""
    payload = {
        "targetOrigins": CYBERSOURCE_TARGET_ORIGINS,
        "clientVersion": CYBERSOURCE_CLIENT_VERSION,
        "allowedCardNetworks": CYBERSOURCE_CARD_NETWORKS,
        "allowedPaymentTypes": ["PANENTRY"],
        "country": "LB",
        "locale": "fr_FR" if lang == "fr" else "en_US",
        "captureMandate": {
            "billingType": "NONE",
            "requestEmail": False,
            "requestPhone": False,
            "requestShipping": False,
            "showAcceptedNetworkIcons": True,
        },
        "orderInformation": {"amountDetails": {"totalAmount": amount_text(amount_cents), "currency": CURRENCY}},
    }
    res = _post(CAPTURE_CONTEXT_PATH, payload)
    if res.status_code not in (200, 201):
        logger.error(f"Cybersource capture context refused: {res.status_code} {res.text[:500]}")
        raise GatewayError(f"capture context refused ({res.status_code})")
    # The answer is the JWT itself (application/jwt).
    return res.text.strip().strip('"')


def authorize_and_capture(transient_token: str, amount_cents: int, reference: str, bill_to: dict) -> dict:
    """Charges the card behind the transient token (authorized and captured
    at once). Returns {"approved", "status", "id", "message", "raw"}."""
    payload = {
        "clientReferenceInformation": {"code": reference[:50]},
        "processingInformation": {"capture": True},
        "tokenInformation": {"transientTokenJwt": transient_token},
        "orderInformation": {
            "amountDetails": {"totalAmount": amount_text(amount_cents), "currency": CURRENCY},
            "billTo": {k: v for k, v in bill_to.items() if v},
        },
    }
    res = _post(PAYMENTS_PATH, payload)
    try:
        data = res.json()
    except ValueError:
        data = {}
    if res.status_code >= 500:
        # Their side failed: we can't know whether the card was charged.
        raise GatewayError(f"Cybersource error {res.status_code}: {res.text[:300]}", sent=True)
    status = data.get("status") or ""
    authorized = (data.get("orderInformation") or {}).get("amountDetails", {}).get("authorizedAmount")
    approved = (
        res.status_code in (200, 201)
        and status == "AUTHORIZED"
        and (authorized is None or authorized == amount_text(amount_cents))
    )
    info = data.get("errorInformation") or {}
    return {
        "approved": approved,
        "status": status or f"HTTP {res.status_code}",
        "id": data.get("id"),
        "message": info.get("message") or data.get("message") or "",
        "reason": info.get("reason") or data.get("reason") or "",
        "raw": {k: data.get(k) for k in ("id", "status", "submitTimeUtc", "processorInformation", "errorInformation", "reason", "message")
                if data.get(k) is not None},
    }
