"""An image for the cover can come from the computer, the phone that scanned
the QR code or Google Photos: each is stored as a
cover image, and none adds photos or pages to the album."""
import asyncio
import types
from io import BytesIO

import pytest
from PIL import Image

from tests.test_api import _signup


@pytest.fixture()
def store(monkeypatch):
    from app.routers import covers
    from app.services import photos

    files = {}

    def get_object(path):
        if path not in files:
            raise FileNotFoundError(path)
        return files[path]

    def put_object(path, data, content_type=None):
        files[path] = (data, content_type)
        return {"path": path, "size": len(data)}

    monkeypatch.setattr(covers, "get_object", get_object)
    monkeypatch.setattr(photos, "put_object", put_object)
    return files


def _jpeg(size=(800, 600)):
    buf = BytesIO()
    Image.new("RGB", size, (120, 140, 160)).save(buf, format="JPEG")
    return buf.getvalue()


def _album(client, db):
    user, headers = _signup(client, db=db)
    album_id = client.post("/api/albums", json={"title": "Cover"}, headers=headers).json()["id"]
    return album_id, headers


def _photo_count(db, album_id):
    return asyncio.run(db.photos.count_documents({"album_id": album_id}))


def test_an_image_without_a_type_is_read_from_its_name(client, db, store):
    """Windows gives an iPhone photo no type: it's still accepted."""
    album_id, headers = _album(client, db)
    res = client.post(
        f"/api/albums/{album_id}/cover-assets",
        files={"file": ("IMG_1.JPG", _jpeg(), "application/octet-stream")},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["storage_path"].endswith(".jpg") and body["storage_path"] in store
    assert (body["photo_width"], body["photo_height"]) == (800, 600)

    refused = client.post(f"/api/albums/{album_id}/cover-assets", files={"file": ("notes.txt", b"hello", "text/plain")}, headers=headers)
    assert refused.status_code == 400


def test_a_google_photo_goes_onto_the_cover(client, db, store, monkeypatch):
    from app.services import google_photos

    asked = []

    def download(url, headers, max_redirects=3):
        asked.append(url)
        return types.SimpleNamespace(status_code=200, headers={"Content-Type": "image/jpeg"}, content=_jpeg())

    monkeypatch.setattr(google_photos, "_download", download)
    album_id, headers = _album(client, db)
    items = [{"mediaFile": {"baseUrl": "https://lh3.googleusercontent.com/abc", "filename": "beach.jpg"}}]
    res = client.post(f"/api/albums/{album_id}/cover-assets/google-photos", json={"access_token": "tok", "items": items}, headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["storage_path"] in store
    assert asked == ["https://lh3.googleusercontent.com/abc=d"]
    assert _photo_count(db, album_id) == 0

    # Only Google's photo servers are fetched.
    bad = [{"mediaFile": {"baseUrl": "https://evil.example.com/x", "filename": "x.jpg"}}]
    assert client.post(f"/api/albums/{album_id}/cover-assets/google-photos", json={"access_token": "tok", "items": bad}, headers=headers).status_code == 400


def test_the_phone_sends_an_image_for_the_cover(client, db, store):
    """A QR code made for the cover: what the phone sends is kept for the
    computer to place, not added to the album's photos."""
    album_id, headers = _album(client, db)
    token = client.post(f"/api/albums/{album_id}/mobile-upload-session", json={"purpose": "cover"}, headers=headers).json()["token"]
    assert client.get(f"/api/mobile-upload/{token}/info").json()["purpose"] == "cover"

    res = client.post(f"/api/mobile-upload/{token}/photos", files=[("files", ("IMG.heic.jpg", _jpeg(), "image/jpeg"))])
    assert res.status_code == 200 and res.json()["uploaded"] == 1
    assert _photo_count(db, album_id) == 0

    status = client.get(f"/api/albums/{album_id}/mobile-upload-session/{token}", headers=headers).json()
    assert len(status["cover_assets"]) == 1
    asset = status["cover_assets"][0]
    assert asset["id"] and asset["storage_path"] in store and asset["photo_width"] == 800

    # A QR code for photos is unchanged.
    plain = client.post(f"/api/albums/{album_id}/mobile-upload-session", headers=headers).json()["token"]
    assert client.get(f"/api/mobile-upload/{plain}/info").json()["purpose"] == "photos"
