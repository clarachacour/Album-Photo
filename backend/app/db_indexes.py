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
    ("photos", [("album_id", ASCENDING), ("content_hash", ASCENDING)], {}),  # skip a photo sent twice
    ("orders", "id", {"unique": True}),
    # One order of each kind (printed book, digital album) per album,
    # enforced by the database too: two checkout requests arriving together
    # can't both create one. Orders from before digital albums have no
    # kind: they're printed ones.
    ("orders", [("album_id", ASCENDING), ("kind", ASCENDING)], {"unique": True}),
    ("orders", "album_id", {}),
    ("orders", "user_id", {}),
    ("orders", "created_at", {}),  # admin order list
    ("pdf_generation_slots", "order_id", {"unique": True}),
    ("mobile_sessions", "token", {"unique": True}),
    ("mobile_sessions", "expires", {"expireAfterSeconds": 0}),
]


# Replaced indexes, removed at startup: (collection, index name).
OBSOLETE_INDEXES = [
    ("orders", "album_id_1"),  # was unique: one order per album, before digital albums
]


async def ensure_indexes(db) -> list:
    """Creates every index; returns the ones that failed. A failure (e.g. a
    unique index over data that already has duplicates) is logged but
    doesn't stop the app from starting: the site keeps working, only
    without that index, until the data is fixed."""
    failed = []
    for collection, name in OBSOLETE_INDEXES:
        try:
            info = await db[collection].index_information()
            if info.get(name, {}).get("unique"):
                await db[collection].drop_index(name)
        except Exception as e:
            logger.error(f"Ancien index {collection}.{name} non supprimé : {e}")
    for collection, keys, options in INDEXES:
        try:
            await db[collection].create_index(keys, **options)
        except Exception as e:
            failed.append((collection, keys))
            logger.error(f"Index {collection}.{keys} non créé : {e}. Vérifiez les doublons dans la collection.")
    return failed
