"""Two tabs (or two devices) editing the same album: a save made on an
outdated copy is refused instead of silently erasing the other change."""
import asyncio
import uuid

from tests.test_api import _signup


def _new_album(client, headers):
    res = client.post("/api/albums", json={"title": "Trip"}, headers=headers)
    assert res.json()["version"] == 0
    return res.json()["id"]


def test_a_save_on_an_outdated_copy_is_refused(client, db):
    _, headers = _signup(client, db=db)
    album_id = _new_album(client, headers)

    # Both tabs opened the album at version 0; the first one saves.
    first = client.patch(f"/api/albums/{album_id}", json={"title": "From tab A", "base_version": 0}, headers=headers)
    assert first.status_code == 200 and first.json()["version"] == 1

    # The second tab, still on version 0, would erase it.
    second = client.patch(f"/api/albums/{album_id}", json={"title": "From tab B", "base_version": 0}, headers=headers)
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "album_changed" and second.json()["detail"]["version"] == 1
    assert client.get(f"/api/albums/{album_id}", headers=headers).json()["title"] == "From tab A"

    # Once it has chosen to keep its own version, it saves on the current one.
    third = client.patch(f"/api/albums/{album_id}", json={"title": "From tab B", "base_version": 1}, headers=headers)
    assert third.status_code == 200 and third.json()["version"] == 2
    assert client.get(f"/api/albums/{album_id}/status", headers=headers).json()["version"] == 2


def test_albums_from_before_versions_count_as_version_0(client, db):
    _, headers = _signup(client, db=db)
    album_id = _new_album(client, headers)
    asyncio.run(db.albums.update_one({"id": album_id}, {"$unset": {"version": ""}}))
    res = client.patch(f"/api/albums/{album_id}", json={"title": "Old", "base_version": 0}, headers=headers)
    assert res.status_code == 200 and res.json()["version"] == 1


def test_a_save_without_a_version_still_works(client, db):
    # The album creation steps save without one.
    _, headers = _signup(client, db=db)
    album_id = _new_album(client, headers)
    client.patch(f"/api/albums/{album_id}", json={"title": "A"}, headers=headers)
    res = client.patch(f"/api/albums/{album_id}", json={"title": "B"}, headers=headers)
    assert res.status_code == 200 and res.json()["version"] == 2


def test_photos_laid_out_while_the_person_saves_keep_the_saved_edit(client, db, monkeypatch):
    from app.services import processing

    _, headers = _signup(client, db=db)
    album_id = _new_album(client, headers)
    title = {"id": "title", "items": []}
    edited = {"id": "mine", "items": [{"type": "text", "content": "My caption"}]}
    asyncio.run(db.albums.update_one({"id": album_id}, {"$set": {"status": "ready", "target_pages": 50, "pages": [title]}}))
    ids = [str(uuid.uuid4()) for _ in range(3)]
    asyncio.run(db.photos.insert_many([
        {"id": i, "album_id": album_id, "user_id": "u", "is_deleted": False, "is_selected": True, "width": 4000, "height": 3000} for i in ids
    ]))

    async def curation_during_which_the_person_saves(photos, existing_selected=None):
        # The editor saves an edit while the new photos are being sorted.
        await db.albums.update_one({"id": album_id}, {"$set": {"pages": [title, edited]}, "$inc": {"version": 1}})
        return list(photos), {}

    monkeypatch.setattr(processing, "curate_photos", curation_during_which_the_person_saves)
    asyncio.run(processing.add_photos_to_layout(album_id, "u", ids))

    album = asyncio.run(db.albums.find_one({"id": album_id}))
    assert [p["id"] for p in album["pages"][:2]] == ["title", "mine"]  # the edit is still there
    placed = {it["photo_id"] for pg in album["pages"] for it in pg["items"] if it.get("type") == "photo"}
    assert placed == set(ids) and album["version"] == 2
