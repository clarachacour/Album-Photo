"""Wakilni, the courier: its API, as documented by Wakilni (auth token,
start bulk / add delivery / end bulk, order status, cancel, areas).

Blocking calls (requests): run them in a thread (run_blocking).
"""
import logging
import time as _time
from typing import Optional

import requests

from app.config import (
    WAKILNI_KEY,
    WAKILNI_PICKUP_AREA,
    WAKILNI_PICKUP_DIRECTIONS,
    WAKILNI_PICKUP_FLOOR,
    WAKILNI_PICKUP_LATITUDE,
    WAKILNI_PICKUP_LONGITUDE,
    WAKILNI_SECRET,
    WAKILNI_URL,
)

logger = logging.getLogger(__name__)

TIMEOUT = 30

# Wakilni's status codes.
PENDING, CONFIRMED, PROCESSING, SUCCESS, FAILED, DECLINED, CANCELED, CLOSED_FAILED, POSTPONED, PENDING_CANCELLATION = 1, 2, 3, 4, 5, 6, 7, 8, 9, 10

# Package types: a photo album travels in a plastic sleeve, no box — the
# closest types by size.
PACKAGE_TYPE = {"A5": 59, "A4": 58}  # small box, regular box
CURRENCY_USD = 1
COLLECTION_PAID, COLLECTION_ON_DELIVERY = 54, 52


class WakilniError(Exception):
    pass


def configured() -> bool:
    return bool(WAKILNI_KEY and WAKILNI_SECRET)


_token = {"value": None, "at": 0.0}


def _auth_token(fresh: bool = False) -> str:
    """The bearer token for the other calls, kept for an hour (asked again
    when Wakilni refuses it)."""
    if not fresh and _token["value"] and _time.time() - _token["at"] < 3600:
        return _token["value"]
    url = f"{WAKILNI_URL}/api/v2/third_party/auth_token"
    credentials = {"key": WAKILNI_KEY, "secret": WAKILNI_SECRET}
    # Documented as a GET with a JSON body; query parameters as a fallback.
    res = requests.request("GET", url, json=credentials, timeout=TIMEOUT)
    if res.status_code >= 400:
        res = requests.get(url, params=credentials, timeout=TIMEOUT)
    body = _json(res)
    token = body.get("token") or (body.get("data") or {}).get("token")
    if res.status_code >= 400 or not token:
        raise WakilniError(f"auth failed ({res.status_code}): {_short(body)}")
    _token.update(value=token, at=_time.time())
    return token


def _json(res) -> dict:
    try:
        body = res.json()
    except ValueError:
        return {"raw": res.text[:500]}
    return body if isinstance(body, dict) else {"data": body}


def _short(body) -> str:
    return str(body)[:500]


def _call(method: str, path: str, json: Optional[dict] = None, params: Optional[dict] = None) -> dict:
    for attempt in (1, 2):
        headers = {"Authorization": f"Bearer {_auth_token(fresh=attempt == 2)}", "Accept": "application/json"}
        res = requests.request(method, f"{WAKILNI_URL}{path}", json=json, params=params, headers=headers, timeout=TIMEOUT)
        if res.status_code == 401 and attempt == 1:
            continue  # token expired: once more with a fresh one
        body = _json(res)
        if res.status_code >= 400:
            raise WakilniError(f"{method} {path} → {res.status_code}: {_short(body)}")
        return body
    raise WakilniError(f"{method} {path}: not authorised")


def _field(body: dict, name: str):
    """A field of a Wakilni answer, at its top level or under "data"."""
    if name in body:
        return body[name]
    data = body.get("data")
    return data.get(name) if isinstance(data, dict) else None


def _number(text: str) -> int:
    """A stable number from one of our ids (Wakilni's references are numbers)."""
    return int("".join(c for c in text if c in "0123456789abcdef")[:12] or "0", 16)


def split_name(full_name: str) -> tuple:
    parts = (full_name or "").split()
    if not parts:
        return "Customer", "-"
    return parts[0], " ".join(parts[1:]) or "-"


def delivery_payload(order: dict, customer: dict) -> dict:
    """The "add delivery" body for one of our printed orders."""
    address = order.get("shipping_address") or {}
    first, last = split_name(address.get("full_name"))
    paid = order.get("status") == "paid" or any(h.get("status") == "paid" for h in order.get("status_history") or [])
    directions = ", ".join(x for x in (address.get("street"), address.get("city"), address.get("additional_info")) if x)
    return {
        "get_order_details": False,
        "get_barcode": False,
        "receiver_id": _number(order.get("user_id") or order["id"]),
        "receiver_first_name": first,
        "receiver_last_name": last,
        "receiver_phone_number": address.get("phone") or "",
        "receiver_email": customer.get("email") or "",
        "receiver_location_id": _number(order["id"]),
        "receiver_building": address.get("building") or "",
        "receiver_directions": directions,
        "receiver_area": address.get("area") or address.get("city") or "",
        "currency": CURRENCY_USD,
        # Already paid (marked so in the admin): nothing to collect.
        # Otherwise the courier collects the order's total in cash.
        "cash_collection_type_id": COLLECTION_PAID if paid else COLLECTION_ON_DELIVERY,
        "collection_amount": 0 if paid else round(order.get("total_price_cents", 0) / 100, 2),
        "note": f"Everbook order #{order['id'][:8]} — photo album, keep flat and dry.",
        "car_needed": False,
        "is_express": False,
        "packages": [
            {
                "quantity": int(order.get("quantity") or 1),
                "type_id": PACKAGE_TYPE.get(order.get("size"), 58),
                "name": f"Photo album — {order.get('album_title') or 'Everbook'}"[:255],
                "sku": order["id"][:8],
            }
        ],
    }


def create_delivery(order: dict, customer: dict) -> dict:
    """Start bulk (pickup at the print shop), add the delivery, end bulk.
    Returns what to keep on the order."""
    pickup = {"location_id": 1, "floor": WAKILNI_PICKUP_FLOOR, "area": WAKILNI_PICKUP_AREA}
    if WAKILNI_PICKUP_LATITUDE and WAKILNI_PICKUP_LONGITUDE:
        pickup.update(latitude=WAKILNI_PICKUP_LATITUDE, longitude=WAKILNI_PICKUP_LONGITUDE)
    started = _call("POST", "/api/v2/clients/start_bulk", json=pickup)
    bulk_id = _field(started, "bulk_id")
    if not bulk_id:
        raise WakilniError(f"start_bulk gave no bulk_id: {_short(started)}")
    added = _call("POST", f"/api/v2/clients/add_delivery/{bulk_id}", json=delivery_payload(order, customer))
    delivery_id = _field(added, "delivery_id")
    if not delivery_id:
        raise WakilniError(f"add_delivery gave no delivery_id: {_short(added)}")
    _call("POST", f"/api/v2/clients/end_bulk/{bulk_id}")
    return {
        "provider": "wakilni",
        "bulk_id": bulk_id,
        "delivery_id": delivery_id,
        "tracking_id": _field(added, "tracking_id"),
        "tracking_url": _field(added, "tracking_url"),
        "pickup_note": WAKILNI_PICKUP_DIRECTIONS,
    }


def delivery_status(delivery_id) -> dict:
    """{"code", "label", "rejected"}: the latest status of a delivery."""
    body = _call("GET", "/api/v2/clients/orders/status", params={"order_id": delivery_id})
    logs = _field(body, "logs") or []
    if logs:
        latest = max(logs, key=lambda log: (log.get("created_at") or "", log.get("status_code") or 0))
        label = latest.get("status") or ""
        # "Success" and "Success, Rejected" share code 4 and a time: the
        # rejection, when there's one, is what counts.
        rejected = any("reject" in (log.get("status") or "").lower() and log.get("created_at") == latest.get("created_at") for log in logs)
        return {"code": latest.get("status_code"), "label": label, "rejected": rejected}
    status = _call("POST", f"/api/v2/clients/orders/{delivery_id}")
    label = str(_field(status, "status") or "")
    return {"code": _field(status, "status_code"), "label": label, "rejected": "reject" in label.lower()}


def cancel_delivery(delivery_id, reason: str) -> dict:
    return _call("PUT", f"/api/v2/clients/orders/{delivery_id}/cancel", json={"reason": reason})


_areas = {"names": None, "at": 0.0}


def area_names() -> list:
    """Wakilni's area names (for the delivery address), kept for a day."""
    if _areas["names"] is not None and _time.time() - _areas["at"] < 86400:
        return _areas["names"]
    body = _call("GET", "/api/v2/areas")
    items = body.get("data") if isinstance(body.get("data"), list) else (_field(body, "areas") or [])
    if isinstance(items, dict):
        items = items.get("data") or []
    names = sorted({(a.get("name") or "").strip() for a in items if isinstance(a, dict) and a.get("name")})
    _areas.update(names=names, at=_time.time())
    return names
