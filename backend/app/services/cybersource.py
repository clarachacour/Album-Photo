"""Card payment: Cybersource (Visa) Unified Checkout, through areeba.

What areeba's guide describes (Unified Checkout Integration):
- every call to Cybersource is signed: a digest of the body (SHA-256) and an
  HMAC-SHA256 signature of the main headers, with the outlet's API key;
- POST /uc/v1/sessions opens a checkout session for an amount: a JWT the
  site's page uses to show Cybersource's card form (the card is typed there,
  never on our site); the form returns the result (a JWT) to the page.

What the guide leaves out, done the standard Cybersource way: the result
comes through the customer's browser, so it's never trusted on its own —
the transaction is read from Cybersource (GET /tss/v2/transactions/{id})
before anything is ordered; and an authorization isn't money received: one
not captured yet is captured (POST /pts/v2/payments/{id}/captures).

The keys live on Cloud Run (config.CYBS_*), never in the code or logs."""
import base64
import hashlib
import hmac
import json
import logging
from email.utils import formatdate
from typing import Optional

import requests

from app import config

logger = logging.getLogger(__name__)

HOSTS = {"test": "apitest.cybersource.com", "production": "api.cybersource.com"}


class CybersourceError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


def enabled() -> bool:
    return bool(config.CYBS_MERCHANT_ID and config.CYBS_KEY_ID and config.CYBS_SHARED_SECRET)


def host() -> str:
    return HOSTS["production" if config.CYBS_ENV == "production" else "test"]


def _hmac_key() -> bytes:
    # The shared secret areeba gives is Base64: the HMAC key is its bytes.
    secret = config.CYBS_SHARED_SECRET or ""
    try:
        return base64.b64decode(secret, validate=True)
    except Exception:
        return secret.encode()


def signed_headers(method: str, path: str, body: Optional[str] = None, date: Optional[str] = None) -> dict:
    """The headers of a signed call (guide, step 1): host, date,
    v-c-merchant-id, and for a body its digest; then the signature over
    them, (request-target) included."""
    date = date or formatdate(usegmt=True)
    headers = {"host": host(), "date": date, "v-c-merchant-id": config.CYBS_MERCHANT_ID or ""}
    names = ["host", "date", "(request-target)"]
    values = {"host": headers["host"], "date": date, "(request-target)": f"{method.lower()} {path}"}
    if body is not None:
        digest = "SHA-256=" + base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode()
        headers["digest"] = digest
        values["digest"] = digest
        names.append("digest")
        headers["Content-Type"] = "application/json"
    names.append("v-c-merchant-id")
    values["v-c-merchant-id"] = headers["v-c-merchant-id"]
    to_sign = "\n".join(f"{name}: {values[name]}" for name in names)
    signature = base64.b64encode(hmac.new(_hmac_key(), to_sign.encode("utf-8"), hashlib.sha256).digest()).decode()
    headers["signature"] = (
        f'keyid="{config.CYBS_KEY_ID}", algorithm="HmacSHA256", headers="{" ".join(names)}", signature="{signature}"'
    )
    return headers


def _call(method: str, path: str, payload: Optional[dict] = None) -> requests.Response:
    body = json.dumps(payload, separators=(",", ":")) if payload is not None else None
    headers = signed_headers(method, path, body)
    url = f"https://{host()}{path}"
    try:
        resp = requests.request(method, url, data=body, headers=headers, timeout=25)
    except Exception as e:
        raise CybersourceError("unreachable", str(e)[:200]) from None
    # (A transaction looked up and not found yet is expected, not a refusal.)
    if resp.status_code >= 300 and not (method == "GET" and resp.status_code == 404):
        _log_refused(method, url, headers, body, resp)
    return resp


def _log_refused(method: str, url: str, headers: dict, body: Optional[str], resp) -> None:
    """The whole exchange of a refused call, as areeba's support asks for it
    (endpoint, request headers and body, full response). Nothing secret: the
    shared secret is never sent, only the signature made with it, which
    expires with its date."""
    try:
        resp_headers = dict(resp.headers or {})
    except Exception:
        resp_headers = {}
    logger.warning("Diagnostic Cybersource: " + json.dumps({
        "endpoint": f"{method} {url}",
        "request_headers": headers,
        "request_body": json.loads(body) if body else None,
        "response_status": resp.status_code,
        "response_headers": resp_headers,
        "response_body": (resp.text or "")[:4000],
    }, ensure_ascii=False))


def create_session(amount_cents: int, target_origins: list, reference: str, locale: str = "en_US") -> str:
    """A Unified Checkout session for this amount in US dollars: the JWT
    the page loads the card form with (guide, step 2)."""
    payload = {
        "targetOrigins": target_origins,
        "country": "LB",
        "locale": locale,
        # No billing address (no postal code to type: most customers in
        # Lebanon have none). If the account requires one, the session is
        # refused and asked again with the partial address (country + code).
        "captureMandate": {"billingType": "NONE", "requestShipping": False, "showConfirmationStep": False, "requestSaveCredentials": False},
        "data": {
            "clientReferenceInformation": {"code": reference},
            "orderInformation": {"amountDetails": {"totalAmount": f"{amount_cents / 100:.2f}", "currency": "USD"}},
        },
    }
    resp = _call("POST", "/uc/v1/sessions", payload)
    if resp.status_code == 400:
        logger.warning(f"Session carte refusée sans adresse de facturation ({resp.text[:200]}), nouvel essai avec")
        payload["captureMandate"]["billingType"] = "PARTIAL"
        resp = _call("POST", "/uc/v1/sessions", payload)
    if resp.status_code == 400:
        # Our reference isn't in areeba's guide: if the session refuses it,
        # one without (the transaction is then matched by its id and amount).
        logger.warning(f"Session carte refusée avec la référence ({resp.text[:200]}), nouvel essai sans")
        payload["data"].pop("clientReferenceInformation", None)
        resp = _call("POST", "/uc/v1/sessions", payload)
    if resp.status_code >= 300:
        raise CybersourceError(f"session_{resp.status_code}", resp.text[:300])
    jwt = resp.text.strip().strip('"')
    if jwt.count(".") != 2:
        raise CybersourceError("session_not_jwt", jwt[:100])
    return jwt


def transaction(transaction_id: str) -> Optional[dict]:
    """The transaction as Cybersource has it (None: not found yet — it can
    take a few seconds to appear)."""
    resp = _call("GET", f"/tss/v2/transactions/{transaction_id}")
    if resp.status_code == 404:
        return None
    if resp.status_code >= 300:
        raise CybersourceError(f"transaction_{resp.status_code}", resp.text[:300])
    return resp.json()


def find_by_reference(reference: str) -> Optional[str]:
    """The id of the latest transaction with our reference (Transaction
    Search), when the browser never sent the result back; None if none."""
    resp = _call("POST", "/tss/v2/searches", {
        "save": False, "name": "everbook-reference", "timezone": "UTC",
        "query": f"clientReferenceInformation.code:{reference}", "offset": 0, "limit": 5, "sort": "id:desc,submitTimeUtc:desc",
    })
    if resp.status_code >= 300:
        raise CybersourceError(f"search_{resp.status_code}", resp.text[:300])
    found = ((resp.json().get("_embedded") or {}).get("transactionSummaries") or [])
    return found[0].get("id") if found else None


def capture(transaction_id: str, amount_cents: int, reference: str) -> dict:
    """Captures (collects) an authorized payment, for its full amount."""
    resp = _call("POST", f"/pts/v2/payments/{transaction_id}/captures", {
        "clientReferenceInformation": {"code": reference},
        "orderInformation": {"amountDetails": {"totalAmount": f"{amount_cents / 100:.2f}", "currency": "USD"}},
    })
    data = resp.json() if resp.content else {}
    if resp.status_code >= 300 or str(data.get("status", "")).upper() not in ("PENDING", "TRANSMITTED", "CAPTURED", "SETTLED"):
        raise CybersourceError(f"capture_{resp.status_code}", json.dumps(data)[:300])
    return data


def read_transaction(tx: dict) -> dict:
    """What matters in a transaction (Transaction Details): whether it was
    authorized, captured, for how much, in which currency, our reference."""
    apps = {a.get("name"): a for a in ((tx.get("applicationInformation") or {}).get("applications") or [])}

    def ok(name):
        app = apps.get(name)
        return bool(app) and str(app.get("rCode", app.get("reasonCode", ""))) in ("1", "100")

    amounts = (tx.get("orderInformation") or {}).get("amountDetails") or {}
    amount = amounts.get("authorizedAmount") or amounts.get("totalAmount")
    try:
        cents = round(float(amount) * 100) if amount is not None else None
    except (TypeError, ValueError):
        cents = None
    return {
        "authorized": ok("ics_auth"),
        "captured": ok("ics_bill"),
        "declined": "ics_auth" in apps and not ok("ics_auth"),
        "amount_cents": cents,
        "currency": str(amounts.get("currency") or "").upper(),
        "reference": (tx.get("clientReferenceInformation") or {}).get("code"),
        "applications": sorted(apps),
    }


def result_transaction_id(result_jwt: str) -> Optional[str]:
    """The transaction id in the card form's result (a JWT the browser
    sends): only used to look the transaction up at Cybersource."""
    try:
        payload = result_jwt.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return None
    return data.get("id") or (data.get("details") or {}).get("id")
