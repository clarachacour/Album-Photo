"""Database indexes (app/db_indexes.py)."""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient
from pymongo.errors import DuplicateKeyError

from app.db_indexes import INDEXES, ensure_indexes


def _index_keys(db, collection):
    info = asyncio.run(db[collection].index_information())
    return [tuple(k for k, _ in spec["key"]) for spec in info.values()]


def test_every_index_exists_after_startup(client, db):
    for collection, keys, _ in INDEXES:
        wanted = (keys,) if isinstance(keys, str) else tuple(k for k, _ in keys)
        assert wanted in _index_keys(db, collection), f"{collection}.{keys}"


def test_one_order_per_album_is_enforced_by_the_database(client, db):
    asyncio.run(db.orders.insert_one({"id": "o-1", "album_id": "album-dup"}))
    with pytest.raises(DuplicateKeyError):
        asyncio.run(db.orders.insert_one({"id": "o-2", "album_id": "album-dup"}))


def test_existing_duplicates_dont_stop_startup():
    db = AsyncMongoMockClient()["indexes_test"]

    async def run():
        await db.orders.insert_many([{"id": "a", "album_id": "same"}, {"id": "b", "album_id": "same"}])
        return await ensure_indexes(db)

    failed = asyncio.run(run())
    assert failed == [("orders", "album_id")]  # logged; every other index is created
