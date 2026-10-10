"""'Brighten' in the editor: a lighter copy of a dark photo."""
import asyncio
import io

from PIL import Image

from tests.test_api import _signup


def _dark_jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (300, 200), (30, 26, 22)).save(buf, "JPEG")
    return buf.getvalue()


def test_brighten_makes_one_lighter_copy_per_level(client, db, monkeypatch):
    from app.services import photos

    files = {"u/a/dark.jpg": _dark_jpeg()}
    monkeypatch.setattr(photos, "get_object", lambda path: (files[path], "image/jpeg"))
    monkeypatch.setattr(photos, "put_object", lambda path, body, ct=None: files.__setitem__(path, body) or {"path": path, "size": len(body)})

    _, headers = _signup(client, db=db)
    album_id = client.post("/api/albums", json={"title": "Night"}, headers=headers).json()["id"]
    user_id = client.get("/api/auth/me", headers=headers).json()["id"]
    asyncio.run(db.photos.insert_one({
        "id": "dark", "album_id": album_id, "user_id": user_id, "storage_path": "u/a/dark.jpg",
        "content_type": "image/jpeg", "width": 300, "height": 200, "brightness": 0.1, "is_deleted": False,
    }))

    url = f"/api/albums/{album_id}/photos/dark/brighten"
    light = client.post(f"{url}?level=light", headers=headers).json()
    assert light["derived_from"] == "dark" and light["brighten_level"] == "light"
    assert light["brightness"] > 0.3 and (light["width"], light["height"]) == (300, 200)
    # Asked again (or from the copy itself): the same copy, not a new one.
    assert client.post(f"{url}?level=light", headers=headers).json()["id"] == light["id"]
    strong = client.post(f"/api/albums/{album_id}/photos/{light['id']}/brighten?level=strong", headers=headers).json()
    assert strong["derived_from"] == "dark" and strong["brightness"] > light["brightness"]
    assert client.post(f"{url}?level=max", headers=headers).status_code == 400
