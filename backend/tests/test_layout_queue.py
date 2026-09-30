"""Photos added to an album already laid out, several batches at once:
every photo ends up on a page, once, and the album doesn't stay locked."""
import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture()
def slow_curation(monkeypatch):
    """Curation that keeps every photo and takes a moment — long enough for
    batches processed side by side to overlap, as they do for real."""
    from app.services import processing

    async def curate(photos, existing_selected=None):
        await asyncio.sleep(random.uniform(0.01, 0.05))
        return list(photos), {"total_in": len(photos)}

    monkeypatch.setattr(processing, "curate_photos", curate)

    # Real database calls take a few milliseconds: a moment between reading
    # the pages and saving them, where another batch can slip in. The
    # in-memory test database answers instantly, so it's made explicit here.
    real_trim = processing.trim_pages_to_target

    async def trim(pages, target_pages):
        await asyncio.sleep(random.uniform(0.005, 0.02))
        return await real_trim(pages, target_pages)

    monkeypatch.setattr(processing, "trim_pages_to_target", trim)


def _album(db, status="ready", pages=None):
    album_id = str(uuid.uuid4())
    title = {"id": "title", "items": [{"type": "text", "content": "Title"}]}
    asyncio.run(db.albums.insert_one({"id": album_id, "user_id": "u1", "status": status, "orientation": "portrait", "target_pages": 250, "pages": pages or [title]}))
    return album_id


def _photos(db, album_id, n):
    ids = [str(uuid.uuid4()) for _ in range(n)]
    asyncio.run(db.photos.insert_many([{"id": i, "album_id": album_id, "user_id": "u1", "is_deleted": False, "is_selected": True, "width": 4000, "height": 3000} for i in ids]))
    return ids


def _placed(db, album_id):
    album = asyncio.run(db.albums.find_one({"id": album_id}))
    return [it["photo_id"] for pg in album["pages"] for it in pg.get("items", []) if it.get("type") == "photo"], album


def test_batches_added_at_the_same_time_are_all_laid_out_once(client, db, slow_curation):
    from app.services.processing import add_photos_to_layout

    album_id = _album(db)
    batches = [_photos(db, album_id, 8) for _ in range(6)]

    async def all_at_once():
        await asyncio.gather(*(add_photos_to_layout(album_id, "u1", ids) for ids in batches))

    asyncio.run(all_at_once())
    placed, album = _placed(db, album_id)
    every = [i for ids in batches for i in ids]
    assert sorted(placed) == sorted(every)  # none lost, none twice
    assert album["pages"][0]["id"] == "title"
    assert album["status"] == "ready" and "layout_lock" not in album
    assert asyncio.run(db.photos.count_documents({"album_id": album_id, "layout_pending": True})) == 0


def test_photos_added_during_the_first_layout_are_laid_out_after_it(client, db, slow_curation):
    from app.services.processing import add_photos_to_layout, run_ai_processing

    album_id = _album(db, status="processing")
    first = _photos(db, album_id, 10)

    async def scenario():
        full = asyncio.create_task(run_ai_processing(album_id, "u1"))
        await asyncio.sleep(0)  # the first layout has taken the lock
        late = _photos_async(db, album_id, 5)
        ids = await late
        await add_photos_to_layout(album_id, "u1", ids)  # lock held: left for the first run
        await full
        return ids

    late = asyncio.run(scenario())
    placed, album = _placed(db, album_id)
    assert sorted(placed) == sorted(first + late)
    assert album["status"] == "ready" and "layout_lock" not in album


async def _photos_async(db, album_id, n):
    ids = [str(uuid.uuid4()) for _ in range(n)]
    await db.photos.insert_many([{"id": i, "album_id": album_id, "user_id": "u1", "is_deleted": False, "is_selected": True, "width": 4000, "height": 3000} for i in ids])
    return ids


def test_a_lock_left_by_a_dead_run_is_taken_over(client, db, slow_curation):
    from app.services.processing import add_photos_to_layout

    album_id = _album(db, status="processing")
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    asyncio.run(db.albums.update_one({"id": album_id}, {"$set": {"layout_lock": old}}))
    ids = _photos(db, album_id, 4)
    asyncio.run(add_photos_to_layout(album_id, "u1", ids))
    placed, album = _placed(db, album_id)
    assert sorted(placed) == sorted(ids)
    assert album["status"] == "ready" and "layout_lock" not in album


def test_a_live_lock_is_respected(client, db, slow_curation):
    from app.services.processing import add_photos_to_layout

    album_id = _album(db, status="processing")
    asyncio.run(db.albums.update_one({"id": album_id}, {"$set": {"layout_lock": datetime.now(timezone.utc).isoformat()}}))
    ids = _photos(db, album_id, 3)
    asyncio.run(add_photos_to_layout(album_id, "u1", ids))
    placed, _ = _placed(db, album_id)
    assert placed == []  # left to the run holding the lock
    assert asyncio.run(db.photos.count_documents({"id": {"$in": ids}, "layout_pending": True})) == 3


def test_a_failed_layout_frees_the_album(client, db, monkeypatch):
    from app.services import processing

    async def broken(photos, existing_selected=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(processing, "curate_photos", broken)
    album_id = _album(db)
    ids = _photos(db, album_id, 3)
    asyncio.run(processing.add_photos_to_layout(album_id, "u1", ids))
    album = asyncio.run(db.albums.find_one({"id": album_id}))
    assert album["status"] == "error" and "layout_lock" not in album
    assert asyncio.run(db.photos.count_documents({"id": {"$in": ids}, "layout_pending": True})) == 0  # no endless retry
