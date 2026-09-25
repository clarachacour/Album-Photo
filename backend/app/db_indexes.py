"""MongoDB indexes, created at startup (creating an existing index is a
no-op). Without them every lookup by id reads the whole collection, which
gets slower as the site grows."""
import logging

from pymongo import ASCENDING, DESCENDING

logger = logging.getLogger(__name__)

# (collection, keys, options)
INDEXES = [
    ("users", "email", {"unique": True}),
    ("users", "id", {"unique": True}),  # read on every logged-in request
    ("users", "verify_email_token", {"sparse": True}),
    ("users", "reset_token", {"sparse": True}),
    ("albums", "id", {"unique": True}),
    ("albums", "user_id", {}),
    ("albums", [("user_id", ASCENDING), ("updated_at", DESCENDING)], {}),  # "My albums", newest first
    ("albums", "created_at", {}),  # draft reminders and cleanup
    ("photos", "id", {"unique": True}),  # read for every image shown
    ("photos", "album_id", {}),
    ("orders", "id", {"unique": True}),
    # One order per album, enforced by the database too: two checkout
    # requests arriving together can't both create one.
    ("orders", "album_id", {"unique": True}),
    ("orders", "user_id", {}),
    ("orders", "created_at", {}),  # admin order list
    ("pdf_generation_slots", "order_id", {"unique": True}),
    ("mobile_sessions", "token", {"unique": True}),
    ("mobile_sessions", "expires", {"expireAfterSeconds": 0}),
]


async def ensure_indexes(db) -> list:
    """Creates every index; returns the ones that failed. A failure (e.g. a
    unique index over data that already has duplicates) is logged but
    doesn't stop the app from starting: the site keeps working, only
    without that index, until the data is fixed."""
    failed = []
    for collection, keys, options in INDEXES:
        try:
            await db[collection].create_index(keys, **options)
        except Exception as e:
            failed.append((collection, keys))
            logger.error(f"Index {collection}.{keys} non créé : {e}. Vérifiez les doublons dans la collection.")
    return failed
