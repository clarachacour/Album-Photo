"""An album never stays stuck on "creating your album": the layout goes
through the queue, keeps its lock alive, and a run that died is started
again as soon as someone looks at the album."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_api import _signup

SECRET = "task-secret"


def _user_id(headers):
    from app.core.auth import decode_token

    return decode_token(headers["Authorization"].split()[1])


def _album(client, db, headers, n_photos=4, **fields):
    album_id = client.post("/api/albums", json={"title": "Trip"}, headers=headers).json()["id"]
    user_id = _user_id(headers)
    asyncio.run(db.albums.update_one({"id": album_id}, {"$set": {"target_pages": 4, **fields}}))
    ids = [str(uuid.uuid4()) for _ in range(n_photos)]
    asyncio.run(db.photos.insert_many([
        {"id": i, "album_id": album_id, "user_id": user_id, "is_deleted": False, "is_selected": True, "width": 4000, "height": 3000}
        for i in ids
    ]))
    return album_id, ids


def _ago(minutes):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _placed(db, album_id):
    album = asyncio.run(db.albums.find_one({"id": album_id}))
    return {it["photo_id"] for pg in album["pages"] for it in pg.get("items", []) if it.get("type") == "photo"}, album


@pytest.fixture()
def queue(monkeypatch):
    from app.routers import internal
    from app.services import processing

    queued = []
    monkeypatch.setattr(processing, "pdf_tasks_enabled", lambda: True)
    monkeypatch.setattr(processing, "enqueue_album_layout", queued.append)
    monkeypatch.setattr(internal, "CLEANUP_SECRET", SECRET)
    return queued


def test_the_layout_goes_through_the_queue(client, db, slow_curation, queue):
    _, headers = _signup(client, db=db)
    album_id, ids = _album(client, db, headers)

    res = client.post(f"/api/albums/{album_id}/process", headers=headers)
    assert res.status_code == 200 and res.json()["queued"] is True
    assert queue == [album_id]
    assert client.get(f"/api/albums/{album_id}/status", headers=headers).json()["status"] == "processing"

    # The queue calls back; the page following the status then sees it ready.
    assert client.post(f"/api/internal/albums/{album_id}/layout", headers={"X-Cleanup-Secret": "wrong"}).status_code == 401
    assert client.post(f"/api/internal/albums/{album_id}/layout", headers={"X-Cleanup-Secret": SECRET}).json()["status"] == "ready"
    placed, album = _placed(db, album_id)
    assert placed == set(ids) and "layout_full_pending" not in album and "layout_lock" not in album
    assert client.get(f"/api/albums/{album_id}/status", headers=headers).json()["status"] == "ready"


def test_without_a_queue_the_layout_is_done_in_the_request(client, db, slow_curation):
    _, headers = _signup(client, db=db)
    album_id, ids = _album(client, db, headers)
    res = client.post(f"/api/albums/{album_id}/process", headers=headers)
    assert res.json() == {"status": "ready", "queued": False, "photo_count": 4}
    assert _placed(db, album_id)[0] == set(ids)


def test_a_first_layout_that_died_is_started_again(client, db, slow_curation):
    _, headers = _signup(client, db=db)
    # Server restarted in the middle: still "processing", lock long gone quiet.
    album_id, ids = _album(client, db, headers, status="processing", layout_full_pending=True, layout_lock=_ago(10), layout_requested_at=_ago(12))

    assert client.get(f"/api/albums/{album_id}/status", headers=headers).json()["status"] == "ready"
    placed, album = _placed(db, album_id)
    assert placed == set(ids) and "layout_lock" not in album


def test_a_dead_run_is_restarted_through_the_queue_once(client, db, slow_curation, queue):
    _, headers = _signup(client, db=db)
    album_id, _ = _album(client, db, headers, status="processing", layout_full_pending=True, layout_lock=_ago(10))
    for _ in range(3):  # the page polls every few seconds
        assert client.get(f"/api/albums/{album_id}/status", headers=headers).json()["status"] == "processing"
    assert queue == [album_id]


def test_photos_left_pending_by_a_dead_run_are_laid_out(client, db, slow_curation):
    _, headers = _signup(client, db=db)
    album_id, ids = _album(client, db, headers, status="processing", layout_lock=_ago(10))
    asyncio.run(db.photos.update_many({"id": {"$in": ids}}, {"$set": {"layout_pending": True}}))
    assert client.get(f"/api/albums/{album_id}/status", headers=headers).json()["status"] == "ready"
    assert _placed(db, album_id)[0] == set(ids)


def test_a_run_that_died_after_its_work_just_frees_the_album(client, db, slow_curation):
    _, headers = _signup(client, db=db)
    album_id, _ = _album(client, db, headers, status="processing", layout_lock=_ago(10))
    assert client.get(f"/api/albums/{album_id}/status", headers=headers).json()["status"] == "ready"


def test_a_live_run_is_left_alone(client, db, slow_curation, queue):
    _, headers = _signup(client, db=db)
    album_id, _ = _album(client, db, headers, status="processing", layout_full_pending=True, layout_lock=_ago(1))
    assert client.get(f"/api/albums/{album_id}/status", headers=headers).json()["status"] == "processing"
    assert queue == []


def test_a_long_run_keeps_its_lock_fresh(db, slow_curation, monkeypatch, client):
    from app.services import processing

    monkeypatch.setattr(processing, "LAYOUT_HEARTBEAT_SECONDS", 0.05)
    seen = []

    async def long_curation(photos, existing_selected=None):
        for _ in range(4):
            await asyncio.sleep(0.05)
            seen.append((await db.albums.find_one({"id": album_id}))["layout_lock"])
        return list(photos), {}

    monkeypatch.setattr(processing, "curate_photos", long_curation)
    album_id = str(uuid.uuid4())
    asyncio.run(db.albums.insert_one({"id": album_id, "user_id": "u1", "status": "draft", "target_pages": 4, "pages": []}))
    asyncio.run(db.photos.insert_one({"id": str(uuid.uuid4()), "album_id": album_id, "user_id": "u1", "is_deleted": False, "width": 10, "height": 10}))
    asyncio.run(processing.run_ai_processing(album_id, "u1"))
    assert len(set(seen)) > 1  # refreshed while the work went on
