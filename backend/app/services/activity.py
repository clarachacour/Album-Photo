"""The customers' journey, for the admin's statistics (routers/stats.py).

Albums never ordered are deleted after 30 days (and customers delete their
own), so what they did is kept where it stays: on the account, the first
time each step is reached (users.steps.album / photos / cart), and a count
of albums started per day (stats_daily). One small write each, only the
first time for the steps."""
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


async def count_album_started():
    day = _now().strftime("%Y-%m-%d")
    await db.stats_daily.update_one({"day": day}, {"$inc": {"albums": 1}, "$setOnInsert": {"day": day}}, upsert=True)
