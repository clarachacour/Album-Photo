"""Photos added to an album already laid out, several batches at once:
every photo ends up on a page, once, and the album doesn't stay locked."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone



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


def test_a_full_album_keeps_its_page_count_and_says_how_many_did_not_fit(client, db, slow_curation):
    from app.services.processing import add_photos_to_layout

    title = {"id": "title", "items": []}
    full = [title] + [{"id": f"p{i}", "items": [{"type": "photo", "photo_id": f"x{i}"}]} for i in range(23)]
    album_id = _album(db, pages=full)
    asyncio.run(db.albums.update_one({"id": album_id}, {"$set": {"target_pages": 24}}))
    ids = _photos(db, album_id, 5)
    asyncio.run(add_photos_to_layout(album_id, "u1", ids))
    placed, album = _placed(db, album_id)
    assert len(album["pages"]) == 24  # the page count chosen, not more
    assert not set(ids) & set(placed)
    assert album["unplaced_added"] == 5 and album["unplaced_added_at"]

    # With room, everything is placed and the message goes away.
    asyncio.run(db.albums.update_one({"id": album_id}, {"$set": {"target_pages": 40}}))
    more = _photos(db, album_id, 3)
    asyncio.run(add_photos_to_layout(album_id, "u1", more))
    placed, album = _placed(db, album_id)
    assert set(more) <= set(placed) and album["unplaced_added"] == 0
