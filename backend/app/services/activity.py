"""The customers' journey, for the admin's statistics (routers/stats.py).

Albums never ordered are deleted after 30 days (and customers delete their
own), so what they did is kept where it stays: on the account, the first
time each step is reached (users.steps.album / photos / cart), and per day
the albums started with the choices made (stats_daily: albums, and by
template, pages, size, orientation). One small write each, only the first
time for the steps."""
from datetime import datetime, timezone

from app.db import db

STEPS = ("album", "photos", "cart")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def mark_step(user_id: str, step: str):
    """The first time this account reached this step (kept if already set)."""
    await db.users.update_one(
        {"id": user_id, f"steps.{step}": {"$exists": False}}, {"$set": {f"steps.{step}": _now().isoformat()}}
    )


def _key(value) -> str:
    """A safe field name (no dots or dollars) for a counter."""
    return str(value if value not in (None, "") else "unknown").replace(".", "_").replace("$", "_")[:60]


def album_choices(album: dict) -> dict:
    return {
        "templates": _key(album.get("cover_template_id")),
        "pages": _key(album.get("target_pages")),
        "sizes": _key(album.get("size")),
        "orientations": _key(album.get("orientation")),
    }


async def count_album_started(album: dict):
    day = _now().strftime("%Y-%m-%d")
    inc = {"albums": 1, **{f"{group}.{key}": 1 for group, key in album_choices(album).items()}}
    await db.stats_daily.update_one({"day": day}, {"$inc": inc, "$setOnInsert": {"day": day}}, upsert=True)
