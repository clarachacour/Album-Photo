"""The admin's dashboard: key figures against the period just before (the
same number of days), the money (paid by customers, printing and delivery
costs, margin), the customers' journey (accounts → album → photos → cart →
order), the albums (templates, pages, format: created and ordered, photos),
the orders (printed or PDF, status, PDFs not ready, promo codes, delivery
times, areas), and week by week / month by month. All from the database;
services/activity.py keeps what albums deleted since were. The admin's own
account and orders are left out.

An order here is a checkout (one cart, one or more albums); "albums
ordered" counts each album in it. What customers paid counts gift cards
when they're bought; an order paid with one only counts what was paid on
top (its total is already less the card), so nothing is counted twice."""
from datetime import datetime, timedelta, timezone
from statistics import median

from fastapi import APIRouter, Depends, Query

from app.core.auth import get_current_user, require_admin
from app.core.order_number import order_number
from app.db import db
from app.services.activity import album_choices
from app.services.printer_statement import ENVELOPE_PRICE, printer_unit_price

router = APIRouter()

FUNNEL = ("accounts", "album", "photos", "cart", "ordered")
CHOICES = ("templates", "pages", "sizes", "orientations")
WEEKS = 5
MONTHS = 12

# What Wakilni bills Everbook for one delivery, in cents. Albums delivered
# together (one package) are one delivery: only the order paying it carries
# the delivery price (see print_groups).
DELIVERY_COST_CENTS = 500


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


def _costs(order: dict, album: dict) -> dict:
    """What an order costs Everbook, in cents: the printer's price list
    (see printer_statement) and the delivery. printing is None when the
    price list can't say (an album past 100 pages in an unlisted format)."""
    if order.get("kind", "print") != "print":
        return {"printing": 0, "delivery": 0}
    pages = order.get("page_count") or (album or {}).get("target_pages") or 0
    unit = printer_unit_price(order.get("size"), pages) if pages else None
    quantity = int(order.get("quantity") or 1)
    delivery = DELIVERY_COST_CENTS if int(order.get("shipping_price_cents") or 0) else 0
    return {"printing": round((unit + ENVELOPE_PRICE) * quantity * 100) if unit is not None else None, "delivery": delivery}


def _month_starts(now: datetime, count: int) -> list:
    year, month = now.year, now.month
    starts = []
    for _ in range(count):
        starts.append(f"{year:04d}-{month:02d}-01")
        month -= 1
        if not month:
            year, month = year - 1, 12
    return starts[::-1]


@router.get("/admin/dashboard")
async def admin_dashboard(days: int = Query(30, ge=0, le=3650), user: dict = Depends(get_current_user)):
    """days: the period (0 = since the start), compared with the same
    number of days just before it."""
    require_admin(user)
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).isoformat() if days else ""
    before = (now - timedelta(days=2 * days)).isoformat() if days else None
    others = {"$ne": user["id"]}

    users = _dated(await db.users.find({"id": others}, {"_id": 0, "id": 1, "created_at": 1, "steps": 1}).to_list(100000))
    orders = _dated(await db.orders.find(
        {"user_id": others},
        {"_id": 0, "id": 1, "user_id": 1, "checkout_id": 1, "status": 1, "kind": 1, "quantity": 1, "size": 1,
         "page_count": 1, "total_price_cents": 1, "shipping_price_cents": 1, "promo_code": 1, "promo_discount_cents": 1,
         "created_at": 1, "album_id": 1, "pdf_ready": 1, "pdf_error": 1, "status_history": 1, "shipping_address": 1},
    ).to_list(100000))
    albums = _dated(await db.albums.find(
        {"user_id": others},
        {"_id": 0, "id": 1, "user_id": 1, "created_at": 1, "cover_template_id": 1, "target_pages": 1, "size": 1, "orientation": 1},
    ).to_list(100000))
    counters = await db.stats_daily.find({}, {"_id": 0}).to_list(10000)
    gifts = _dated(await db.gift_cards.find(
        {"buyer_user_id": others}, {"_id": 0, "value_cents": 1, "status": 1, "created_at": 1, "redeemed_at": 1, "expires_at": 1},
    ).to_list(100000))
    messages = _dated(await db.contact_messages.find({}, {"_id": 0, "created_at": 1}).to_list(100000))
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
    costs = {o.get("id"): _costs(o, album_by_id.get(o.get("album_id"))) for o in live}
    # Gift cards paid for (not waiting for payment, not cancelled).
    sold = [g for g in gifts if g.get("status") in ("active", "redeemed", "expired")]

    def money(period_orders: list, period_gifts: list) -> dict:
        orders_paid = sum(int(o.get("total_price_cents") or 0) for o in period_orders)
        gifts_paid = sum(int(g.get("value_cents") or 0) for g in period_gifts)
        printing = sum(costs[o.get("id")]["printing"] or 0 for o in period_orders)
        delivery = sum(costs[o.get("id")]["delivery"] for o in period_orders)
        revenue = orders_paid + gifts_paid
        return {"revenue_cents": revenue, "orders_cents": orders_paid, "gift_cards_cents": gifts_paid,
                "printing_cents": printing, "delivery_cents": delivery, "margin_cents": revenue - printing - delivery,
                "printing_unknown": len([o for o in period_orders if costs[o.get("id")]["printing"] is None])}

    # ---------- Key figures, against the period just before ----------
    def figures(start: str, end: str = None) -> dict:
        period_orders = [o for o in live if _within(o.get("created_at"), start, end)]
        checkouts = {_checkout(o) for o in period_orders}
        m = money(period_orders, [g for g in sold if _within(g.get("created_at"), start, end)])
        return {
            "orders": len(checkouts),
            "albums_ordered": len(period_orders),
            "revenue_cents": m["revenue_cents"],
            "margin_cents": m["margin_cents"],
            "average_order_cents": round(m["orders_cents"] / len(checkouts)) if checkouts else 0,
            "accounts": len([u for u in users if _within(u.get("created_at"), start, end)]),
            "albums_started": started.count(start[:10], end[:10] if end else None),
            "messages": len([m for m in messages if _within(m.get("created_at"), start, end)]),
        }

    current, previous = figures(since), (figures(before, since) if before else None)
    kpis = {k: {"value": v, "previous": previous[k] if previous else None} for k, v in current.items()}
    period_live = [o for o in live if _within(o.get("created_at"), since)]
    money_section = money(period_live, [g for g in sold if _within(g.get("created_at"), since)])

    # ---------- The journey of the accounts created in the period ----------
    new_ids = {u.get("id") for u in users if _within(u.get("created_at"), since)}
    reached = {
        "album": {a.get("user_id") for a in albums},
        "photos": set(await db.photos.distinct("user_id", {"user_id": {"$in": list(new_ids)}})),
        "cart": set(await db.carts.distinct("user_id", {"user_id": {"$in": list(new_ids)}, "items.0": {"$exists": True}})),
        "ordered": {o.get("user_id") for o in live},
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

    # ---------- Albums: created and ordered, by choice ----------
    created_by = {g: {r["key"]: r["count"] for r in rows} for g, rows in started.choices(since[:10]).items()}
    ordered_by = {g: {} for g in CHOICES}
    for o in period_live:
        album = album_by_id.get(o.get("album_id"))
        if album:
            for group, key in album_choices(album).items():
                _add(ordered_by[group], key)
    choices = {}
    for group in CHOICES:
        keys = set(created_by[group]) | set(ordered_by[group])
        rows = [{"key": k, "created": created_by[group].get(k, 0), "ordered": ordered_by[group].get(k, 0)} for k in keys]
        choices[group] = sorted(rows, key=lambda r: (-r["created"], -r["ordered"], r["key"]))
    in_progress = [a for a in albums if a.get("id") not in ordered_album_ids]
    with_photos = [n for n in photo_counts.values() if n]
    albums_section = {
        **choices,
        "photos_per_album": {"average": _avg(with_photos), "median": _median(with_photos), "albums": len(with_photos)},
        "in_progress": len(in_progress),
        "in_progress_without_photos": len([a for a in in_progress if not photo_counts.get(a.get("id"))]),
    }

    # ---------- Orders ----------
    by_status, areas, promos = {}, {}, {}
    for o in orders:
        if _within(o.get("created_at"), since):
            _add(by_status, o.get("status") or "unknown")
    seen_checkouts = set()
    for o in period_live:
        if o.get("promo_code"):
            row = promos.setdefault(o["promo_code"], {"code": o["promo_code"], "orders": set(), "discount_cents": 0})
            row["orders"].add(_checkout(o))
            row["discount_cents"] += int(o.get("promo_discount_cents") or 0)
        address = o.get("shipping_address") or {}
        if address and _checkout(o) not in seen_checkouts:
            seen_checkouts.add(_checkout(o))
            _add(areas, (address.get("area") or address.get("city") or "unknown").strip().title())
    printed = [o for o in period_live if o.get("kind", "print") == "print"]
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
        "printed": {"albums": len(printed), "copies": sum(int(o.get("quantity") or 1) for o in printed)},
        "digital": {"albums": len([o for o in period_live if o.get("kind") == "digital"])},
        "by_status": _ranked(by_status),
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

    # ---------- Gift cards ----------
    now_iso = now.isoformat()
    period_sold = [g for g in sold if _within(g.get("created_at"), since)]
    unused = [g for g in gifts if g.get("status") == "active" and (g.get("expires_at") or "") >= now_iso]
    gift_cards_section = {
        "sold": len(period_sold),
        "sold_cents": sum(int(g.get("value_cents") or 0) for g in period_sold),
        "redeemed": len([g for g in gifts if g.get("status") == "redeemed" and _within(_iso(g.get("redeemed_at")), since)]),
        "unused": len(unused),
        "unused_cents": sum(int(g.get("value_cents") or 0) for g in unused),
        "expired_unused": len([g for g in gifts if g.get("status") in ("active", "expired") and (g.get("expires_at") or "") < now_iso]),
        "waiting_for_payment": len([g for g in gifts if g.get("status") == "pending_payment"]),
    }

    # ---------- Right now ----------
    right_now = {
        "carts_waiting": await db.carts.count_documents({"user_id": others, "items.0": {"$exists": True}}),
        "albums_in_progress": len(in_progress),
        "orders_in_production": len({_checkout(o) for o in live if o.get("status") in ("pending_payment", "paid", "processing", "printing")}),
        "orders_on_their_way": len({_checkout(o) for o in live if o.get("status") in ("ready_for_delivery", "shipped")}),
    }

    # ---------- Over time: week by week (weeks starting on Monday, UTC) and month by month ----------
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    week_starts = [(monday - timedelta(weeks=i)).strftime("%Y-%m-%d") for i in range(WEEKS - 1, -1, -1)]

    def series(starts: list) -> list:
        def bucket(iso):
            day = (iso or "")[:10]
            found = None
            for start in starts:
                if day >= start:
                    found = start
            return found

        rows = {s: {"start": s, "orders": set(), "albums_ordered": 0, "revenue_cents": 0, "margin_cents": 0,
                    "accounts": 0, "albums_started": 0} for s in starts}
        for o in live:
            if (b := bucket(o.get("created_at"))):
                c = costs[o.get("id")]
                rows[b]["orders"].add(_checkout(o))
                rows[b]["albums_ordered"] += 1
                rows[b]["revenue_cents"] += int(o.get("total_price_cents") or 0)
                rows[b]["margin_cents"] += int(o.get("total_price_cents") or 0) - (c["printing"] or 0) - c["delivery"]
        for g in sold:
            if (b := bucket(g.get("created_at"))):
                rows[b]["revenue_cents"] += int(g.get("value_cents") or 0)
                rows[b]["margin_cents"] += int(g.get("value_cents") or 0)
        for u in users:
            if (b := bucket(u.get("created_at"))):
                rows[b]["accounts"] += 1
        for day, n, _ in started.per_day(starts[0]):
            if (b := bucket(day)):
                rows[b]["albums_started"] += n
        return [{**r, "orders": len(r["orders"])} for r in rows.values()]

    return {
        "days": days,
        "generated_at": now.isoformat(),
        "kpis": kpis,
        "money": money_section,
        "funnel": funnel,
        "albums": albums_section,
        "orders": orders_section,
        "gift_cards": gift_cards_section,
        "now": right_now,
        "weekly": series(week_starts),
        "monthly": series(_month_starts(now, MONTHS)),
    }
