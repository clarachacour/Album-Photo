"""The admin's statistics: the customers' journey (accounts → album → photos
→ cart → order), what was ordered over a period, and week by week. All
from the database (services/activity.py keeps the steps of albums deleted
since). The admin's own account and orders are left out."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from app.core.auth import get_current_user, require_admin
from app.db import db

router = APIRouter()

FUNNEL = ("accounts", "album", "photos", "cart", "ordered")
WEEKS = 12


def _checkout(order: dict) -> str:
    return order.get("checkout_id") or order["id"]


async def _albums_started(since_day: str, counters: list) -> dict:
    """Albums started per day: the daily count (stats_daily), and before it
    existed, the albums still in the database (deleted ones are missing)."""
    per_day = {c["day"]: int(c.get("albums") or 0) for c in counters}
    first_counted = min(per_day) if per_day else None
    query = {"created_at": {"$gte": since_day}}
    if first_counted:
        query["created_at"]["$lt"] = first_counted
    for album in await db.albums.find(query, {"_id": 0, "created_at": 1, "user_id": 1}).to_list(100000):
        day = album["created_at"][:10]
        per_day[day] = per_day.get(day, 0) + 1
    return per_day


@router.get("/admin/stats")
async def admin_stats(days: int = Query(30, ge=0, le=3650), user: dict = Depends(get_current_user)):
    """days: the period (0 = since the start)."""
    require_admin(user)
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).isoformat() if days else ""
    not_admin = {"$ne": user["id"]}

    users = await db.users.find({"id": not_admin}, {"_id": 0, "id": 1, "created_at": 1, "steps": 1}).to_list(100000)
    orders = await db.orders.find(
        {"user_id": not_admin},
        {"_id": 0, "id": 1, "user_id": 1, "checkout_id": 1, "status": 1, "kind": 1, "quantity": 1,
         "total_price_cents": 1, "promo_code": 1, "created_at": 1},
    ).to_list(100000)
    live = [o for o in orders if o.get("status") != "cancelled"]

    # The journey of the accounts created in the period: each step counts
    # the accounts that reached it (or a later one: ordering one album
    # straight away skips the cart).
    new = [u for u in users if (u.get("created_at") or "") >= since]
    ids = [u["id"] for u in new]
    reached = {
        "album": set(await db.albums.distinct("user_id", {"user_id": {"$in": ids}})),
        "photos": set(await db.photos.distinct("user_id", {"user_id": {"$in": ids}})),
        "cart": set(await db.carts.distinct("user_id", {"user_id": {"$in": ids}, "items.0": {"$exists": True}})),
        "ordered": {o["user_id"] for o in live},
    }
    for u in new:
        for step in ("album", "photos", "cart"):
            if (u.get("steps") or {}).get(step):
                reached[step].add(u["id"])
    later = set()
    for step in ("ordered", "cart", "photos", "album"):
        reached[step] = (reached[step] | later) & set(ids)
        later = reached[step]
    funnel = [{"step": "accounts", "count": len(ids)}] + [{"step": s, "count": len(reached[s])} for s in FUNNEL[1:]]

    # What happened in the period, for every account.
    counters = await db.stats_daily.find({}, {"_id": 0}).to_list(10000)
    albums_per_day = await _albums_started(since[:10], counters)
    in_period = [o for o in live if (o.get("created_at") or "") >= since]
    checkouts = {_checkout(o) for o in in_period}
    revenue = sum(int(o.get("total_price_cents") or 0) for o in in_period)
    period = {
        "albums_started": sum(n for day, n in albums_per_day.items() if day >= since[:10]),
        "orders": len(checkouts),
        "books": sum(int(o.get("quantity") or 1) for o in in_period if o.get("kind", "print") == "print"),
        "revenue_cents": revenue,
        "average_order_cents": round(revenue / len(checkouts)) if checkouts else 0,
        "with_promo": len({_checkout(o) for o in in_period if o.get("promo_code")}),
        "cancelled": len([o for o in orders if o.get("status") == "cancelled" and (o.get("created_at") or "") >= since]),
        "customers": len({o["user_id"] for o in in_period}),
    }

    # Right now.
    ordered_albums = set(await db.orders.distinct("album_id"))
    current = {
        "carts_waiting": await db.carts.count_documents({"user_id": not_admin, "items.0": {"$exists": True}}),
        "albums_in_progress": await db.albums.count_documents({"user_id": not_admin, "id": {"$nin": list(ordered_albums)}}),
    }

    # Week by week (weeks starting on Monday, UTC), the last WEEKS weeks.
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    starts = [monday - timedelta(weeks=i) for i in range(WEEKS - 1, -1, -1)]
    first_week = starts[0].strftime("%Y-%m-%d")
    week_albums = await _albums_started(first_week, counters)

    def week_of(iso: str):
        day = (iso or "")[:10]
        if day < first_week:
            return None
        found = None
        for start in starts:
            if day >= start.strftime("%Y-%m-%d"):
                found = start.strftime("%Y-%m-%d")
        return found

    weeks = {s.strftime("%Y-%m-%d"): {"week": s.strftime("%Y-%m-%d"), "accounts": 0, "albums": 0, "orders": set(), "revenue_cents": 0} for s in starts}
    for u in users:
        if (w := week_of(u.get("created_at"))):
            weeks[w]["accounts"] += 1
    for day, n in week_albums.items():
        if (w := week_of(day)):
            weeks[w]["albums"] += n
    for o in live:
        if (w := week_of(o.get("created_at"))):
            weeks[w]["orders"].add(_checkout(o))
            weeks[w]["revenue_cents"] += int(o.get("total_price_cents") or 0)
    weekly = [{**w, "orders": len(w["orders"])} for w in weeks.values()]

    return {"days": days, "funnel": funnel, "period": period, "now": current, "weekly": weekly}
