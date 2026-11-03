"""The admin's dashboard: key figures against the period before, the
customers' journey (accounts → album → photos → cart → order), the albums
(templates, pages, photos), the orders (status, PDFs not ready, promo
codes, delivery times, areas), the accounts, the contact messages, and
week by week. All from the database; services/activity.py keeps what
albums deleted since were. The admin's own account and orders are left out."""
from datetime import datetime, timedelta, timezone
from statistics import median

from fastapi import APIRouter, Depends, Query

from app.core.auth import get_current_user, require_admin
from app.core.order_number import order_number
from app.db import db
from app.services.activity import album_choices

router = APIRouter()

FUNNEL = ("accounts", "album", "photos", "cart", "ordered")
CHOICES = ("templates", "pages", "sizes", "orientations")
WEEKS = 12


def _iso(value):
    """A date as the ISO text the comparisons use (older documents may hold
    a datetime)."""
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    return value


def _dated(docs: list) -> list:
    for doc in docs:
        doc["created_at"] = _iso(doc.get("created_at"))
        for h in doc.get("status_history") or []:
            h["at"] = _iso(h.get("at"))
    return docs


def _checkout(order: dict) -> str:
    return order.get("checkout_id") or order.get("id")


def _within(iso, start: str, end: str = None) -> bool:
    iso = iso or ""
    return iso >= start and (end is None or iso < end)


def _ranked(counts: dict, limit: int = None) -> list:
    rows = sorted(({"key": k, "count": n} for k, n in counts.items() if n), key=lambda r: (-r["count"], r["key"]))
    return rows[:limit] if limit else rows


def _add(counts: dict, key, n: int = 1):
    counts[key] = counts.get(key, 0) + n


def _avg(values: list):
    return round(sum(values) / len(values), 1) if values else None


def _median(values: list):
    return round(median(values), 1) if values else None


def _days_between(start_iso: str, end_iso: str):
    try:
        return (datetime.fromisoformat(end_iso) - datetime.fromisoformat(start_iso)).total_seconds() / 86400
    except (TypeError, ValueError):
        return None


class AlbumsStarted:
    """Albums started per day with their choices: the daily counts
    (stats_daily) and, before they existed, the albums still in the
    database (deleted ones are missing there)."""

    def __init__(self, counters: list, albums: list):
        self.counters = counters
        self.first_counted = min((c["day"] for c in counters), default=None)
        self.albums = albums

    def per_day(self, start_day: str, end_day: str = None) -> list:
        """[(day, albums, {group: {key: albums}})] in [start_day, end_day)."""
        rows = []
        for c in self.counters:
            if c["day"] >= start_day and (end_day is None or c["day"] < end_day):
                rows.append((c["day"], int(c.get("albums") or 0), {g: c.get(g) or {} for g in CHOICES}))
        for album in self.albums:
            day = (album.get("created_at") or "")[:10]
            if self.first_counted and day >= self.first_counted:
                continue
            if day >= start_day and (end_day is None or day < end_day):
                rows.append((day, 1, {g: {k: 1} for g, k in album_choices(album).items()}))
        return rows

    def count(self, start_day: str, end_day: str = None) -> int:
        return sum(n for _, n, _ in self.per_day(start_day, end_day))

    def choices(self, start_day: str) -> dict:
        totals = {g: {} for g in CHOICES}
        for _, _, groups in self.per_day(start_day):
            for group, counts in groups.items():
                for key, n in counts.items():
                    _add(totals[group], key, int(n))
        return {g: _ranked(c) for g, c in totals.items()}


@router.get("/admin/dashboard")
async def admin_dashboard(days: int = Query(30, ge=0, le=3650), user: dict = Depends(get_current_user)):
    """days: the period (0 = since the start), compared with the same
    number of days before it."""
    require_admin(user)
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).isoformat() if days else ""
    before = (now - timedelta(days=2 * days)).isoformat() if days else None
    others = {"$ne": user["id"]}

    users = _dated(await db.users.find(
        {"id": others},
        {"_id": 0, "id": 1, "created_at": 1, "steps": 1, "email_verified": 1, "lang": 1, "auth_provider": 1},
    ).to_list(100000))
    orders = _dated(await db.orders.find(
        {"user_id": others},
        {"_id": 0, "id": 1, "user_id": 1, "checkout_id": 1, "status": 1, "kind": 1, "quantity": 1, "size": 1,
         "total_price_cents": 1, "promo_code": 1, "promo_discount_cents": 1, "created_at": 1, "album_id": 1,
         "pdf_ready": 1, "pdf_error": 1, "status_history": 1, "shipping_address": 1},
    ).to_list(100000))
    albums = _dated(await db.albums.find(
        {"user_id": others},
        {"_id": 0, "id": 1, "user_id": 1, "created_at": 1, "cover_template_id": 1, "target_pages": 1, "size": 1, "orientation": 1},
    ).to_list(100000))
    counters = await db.stats_daily.find({}, {"_id": 0}).to_list(10000)
    messages = _dated(await db.contact_messages.find({}, {"_id": 0, "created_at": 1, "subject": 1}).to_list(100000))
    photo_counts = {
        row["_id"]: row["n"]
        for row in await db.photos.aggregate([
            {"$match": {"is_deleted": {"$ne": True}}},
            {"$group": {"_id": "$album_id", "n": {"$sum": 1}}},
        ]).to_list(100000)
    }

    live = [o for o in orders if o.get("status") != "cancelled"]
    started = AlbumsStarted(counters, albums)
    album_by_id = {a.get("id"): a for a in albums}
    ordered_album_ids = {o.get("album_id") for o in live}
    ever_ordered = {o.get("user_id") for o in live}

    # ---------- Key figures, against the period before ----------
    def figures(start: str, end: str = None) -> dict:
        new = [u for u in users if _within(u.get("created_at"), start, end)]
        period_orders = [o for o in live if _within(o.get("created_at"), start, end)]
        checkouts = {_checkout(o) for o in period_orders}
        revenue = sum(int(o.get("total_price_cents") or 0) for o in period_orders)
        return {
            "accounts": len(new),
            "albums_started": started.count(start[:10], end[:10] if end else None),
            "orders": len(checkouts),
            "books": sum(int(o.get("quantity") or 1) for o in period_orders if o.get("kind", "print") == "print"),
            "revenue_cents": revenue,
            "average_order_cents": round(revenue / len(checkouts)) if checkouts else 0,
            "customers": len({o.get("user_id") for o in period_orders}),
            "conversion_percent": round(100 * len([u for u in new if u.get("id") in ever_ordered]) / len(new)) if new else 0,
            "messages": len([m for m in messages if _within(m.get("created_at"), start, end)]),
        }

    current, previous = figures(since), (figures(before, since) if before else None)
    kpis = {k: {"value": v, "previous": previous[k] if previous else None} for k, v in current.items()}

    # ---------- The journey of the accounts created in the period ----------
    new_ids = {u.get("id") for u in users if _within(u.get("created_at"), since)}
    reached = {
        "album": {a.get("user_id") for a in albums},
        "photos": set(await db.photos.distinct("user_id", {"user_id": {"$in": list(new_ids)}})),
        "cart": set(await db.carts.distinct("user_id", {"user_id": {"$in": list(new_ids)}, "items.0": {"$exists": True}})),
        "ordered": set(ever_ordered),
    }
    for u in users:
        for step in ("album", "photos", "cart"):
            if (u.get("steps") or {}).get(step):
                reached[step].add(u.get("id"))
    later = set()
    for step in ("ordered", "cart", "photos", "album"):  # ordering straight away skips the cart
        reached[step] = (reached[step] | later) & new_ids
        later = reached[step]
    funnel = [{"step": "accounts", "count": len(new_ids)}] + [{"step": s, "count": len(reached[s])} for s in FUNNEL[1:]]

    # ---------- Albums ----------
    period_live = [o for o in live if _within(o.get("created_at"), since)]
    ordered_choices = {g: {} for g in CHOICES}
    for o in period_live:
        album = album_by_id.get(o.get("album_id"))
        if album:
            for group, key in album_choices(album).items():
                _add(ordered_choices[group], key)
    in_progress = [a for a in albums if a.get("id") not in ordered_album_ids]
    week_ago = (now - timedelta(days=7)).isoformat()
    photos_in_progress = [photo_counts[a.get("id")] for a in in_progress if photo_counts.get(a.get("id"))]
    photos_ordered = [photo_counts[a] for a in {o.get("album_id") for o in period_live} if photo_counts.get(a)]
    albums_section = {
        "started": current["albums_started"],
        "started_by": started.choices(since[:10]),
        "ordered_by": {g: _ranked(c) for g, c in ordered_choices.items()},
        "in_progress": len(in_progress),
        "in_progress_without_photos": len([a for a in in_progress if not photo_counts.get(a.get("id"))]),
        "in_progress_older_than_7_days": len([a for a in in_progress if (a.get("created_at") or "") < week_ago]),
        "photos_per_album_in_progress": {"average": _avg(photos_in_progress), "median": _median(photos_in_progress)},
        "photos_per_ordered_album": {"average": _avg(photos_ordered), "median": _median(photos_ordered)},
    }

    # ---------- Orders ----------
    period_all = [o for o in orders if _within(o.get("created_at"), since)]
    by_status, by_kind, by_size, areas, promos = {}, {}, {}, {}, {}
    for o in period_all:
        _add(by_status, o.get("status") or "unknown")
    seen_checkouts = set()
    for o in period_live:
        _add(by_kind, o.get("kind") or "print")
        if o.get("kind", "print") == "print":
            _add(by_size, o.get("size") or "unknown", int(o.get("quantity") or 1))
        if o.get("promo_code"):
            row = promos.setdefault(o["promo_code"], {"code": o["promo_code"], "orders": set(), "discount_cents": 0})
            row["orders"].add(_checkout(o))
            row["discount_cents"] += int(o.get("promo_discount_cents") or 0)
        address = o.get("shipping_address") or {}
        if address and _checkout(o) not in seen_checkouts:
            seen_checkouts.add(_checkout(o))
            _add(areas, (address.get("area") or address.get("city") or "unknown").strip().title())
    not_ready = sorted((o for o in live if o.get("kind", "print") == "print" and not o.get("pdf_ready")),
                       key=lambda o: o.get("created_at") or "")
    delivery_days = []
    for o in live:
        delivered = next((h.get("at") for h in o.get("status_history") or [] if h.get("status") == "delivered"), None)
        if delivered and _within(delivered, since):
            d = _days_between(o.get("created_at"), delivered)
            if d is not None:
                delivery_days.append(d)
    checkouts_per_customer = {}
    for o in live:
        checkouts_per_customer.setdefault(o.get("user_id"), set()).add(_checkout(o))
    orders_section = {
        "by_status": _ranked(by_status),
        "by_kind": _ranked(by_kind),
        "books_by_size": _ranked(by_size),
        "areas": _ranked(areas, 8),
        "promo_codes": sorted(({**p, "orders": len(p["orders"])} for p in promos.values()), key=lambda p: -p["orders"]),
        "pdf_not_ready": {
            "count": len(not_ready),
            "orders": [{"number": order_number(o), "created_at": o.get("created_at"), "status": o.get("status"), "failed": bool(o.get("pdf_error"))}
                       for o in not_ready[:20]],
        },
        "delivery_days": {"average": _avg(delivery_days), "median": _median(delivery_days), "orders": len(delivery_days)},
        "customers": len(checkouts_per_customer),
        "repeat_customers": len([c for c in checkouts_per_customer.values() if len(c) >= 2]),
    }

    # ---------- Accounts ----------
    languages, providers = {}, {}
    for u in users:
        _add(languages, u.get("lang") or "unknown")
        _add(providers, u.get("auth_provider") or "email")
    users_section = {
        "total": len(users),
        "new": current["accounts"],
        "verified": len([u for u in users if u.get("email_verified", True)]),
        "with_an_order": len(ever_ordered),
        "languages": _ranked(languages),
        "sign_in": _ranked(providers),
    }

    # ---------- Contact messages ----------
    latest = sorted(messages, key=lambda m: m.get("created_at") or "", reverse=True)[:5]
    messages_section = {"period": current["messages"], "total": len(messages),
                        "latest": [{"subject": m.get("subject"), "created_at": m.get("created_at")} for m in latest]}

    # ---------- Right now ----------
    right_now = {
        "carts_waiting": await db.carts.count_documents({"user_id": others, "items.0": {"$exists": True}}),
        "albums_in_progress": len(in_progress),
        "orders_in_production": len([o for o in live if o.get("status") in ("pending_payment", "paid", "processing", "printing")]),
        "orders_on_their_way": len([o for o in live if o.get("status") in ("ready_for_delivery", "shipped")]),
    }

    # ---------- Week by week (weeks starting on Monday, UTC) ----------
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    starts = [(monday - timedelta(weeks=i)).strftime("%Y-%m-%d") for i in range(WEEKS - 1, -1, -1)]

    def week_of(iso):
        day = (iso or "")[:10]
        found = None
        for start in starts:
            if day >= start:
                found = start
        return found

    weeks = {s: {"week": s, "accounts": 0, "albums": 0, "orders": set(), "revenue_cents": 0, "messages": 0} for s in starts}
    for u in users:
        if (w := week_of(u.get("created_at"))):
            weeks[w]["accounts"] += 1
    for day, n, _ in started.per_day(starts[0]):
        if (w := week_of(day)):
            weeks[w]["albums"] += n
    for o in live:
        if (w := week_of(o.get("created_at"))):
            weeks[w]["orders"].add(_checkout(o))
            weeks[w]["revenue_cents"] += int(o.get("total_price_cents") or 0)
    for m in messages:
        if (w := week_of(m.get("created_at"))):
            weeks[w]["messages"] += 1
    weekly = [{**w, "orders": len(w["orders"])} for w in weeks.values()]

    return {
        "days": days,
        "generated_at": now.isoformat(),
        "kpis": kpis,
        "funnel": funnel,
        "albums": albums_section,
        "orders": orders_section,
        "users": users_section,
        "messages": messages_section,
        "now": right_now,
        "weekly": weekly,
    }
