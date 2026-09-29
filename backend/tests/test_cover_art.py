"""Template logos stored in albums: files, not embedded images."""
import asyncio
import base64
import hashlib
import re
import uuid
from pathlib import Path

from app.services.cover_art import slim_cover, slim_image

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _signup(client, db):
    email = f"{uuid.uuid4().hex[:10]}@example.com"
    token = client.post("/api/auth/signup", json={"email": email, "password": "secret123", "name": "T"}).json()["token"]
    asyncio.run(db.users.update_one({"email": email}, {"$set": {"email_verified": True}}))
    return {"Authorization": f"Bearer {token}"}


def _old_embedded_logo(monkeypatch, url):
    """An embedded image the table maps to `url`, like the ones older albums
    hold (the real ones are no longer in the code; they were checked against
    the table when it was made)."""
    from app.services import cover_art

    embedded = "data:image/png;base64," + base64.b64encode(url.encode() * 50).decode()
    monkeypatch.setitem(cover_art._BY_HASH, hashlib.sha256(embedded.encode()).hexdigest(), url)
    return embedded


def test_every_address_points_to_an_existing_file():
    source = "\n".join(p.read_text() for p in (FRONTEND / "src" / "lib").glob("*.js"))
    urls = set(re.findall(r'"(/cover-art/[^"]+)"', source)) | set(re.findall(r'"(/cover-art/[^"]+)"', (Path(__file__).resolve().parents[1] / "app/services/cover_art.py").read_text()))
    assert len(urls) == 13
    for url in urls:
        assert (FRONTEND / "public" / url.lstrip("/")).is_file(), url


def test_old_small_spine_logo_is_recognised():
    old_mom = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADoAAAA4CAYAAACsc+sjAAAf+UlEQVR42j276Y4cWZqe+ZzVNt9iZwS3JJNLbrV0t9SNqdbM/BAwA93CYPRHlyDdQOuSNAIESQ2NegR0t4RqVWdVZW"
    assert slim_image(old_mom) == "/cover-art/mom-heart-logo-v1.webp"
    assert slim_image("data:image/png;base64,AAAA") == "data:image/png;base64,AAAA"  # someone's own image
    assert slim_image("https://example.com/x.png") == "https://example.com/x.png"


def test_slim_cover_leaves_other_things_alone():
    cover = {"bg_color": "#fff", "extra_items": [{"type": "text", "content": "Hi"}]}
    assert slim_cover(cover) == (cover, False)
    assert slim_cover(None) == (None, False)


def test_older_albums_lose_their_embedded_logos_when_read(client, db, monkeypatch):
    headers = _signup(client, db)
    album_id = client.post("/api/albums", json={"title": "Old"}, headers=headers).json()["id"]
    coral = "/cover-art/coral-logo-v1.webp"
    heart = "/cover-art/heart-logo-v1.webp"
    old_cover = {
        "bg_color": "#009BB5",
        "spine_logo_image": _old_embedded_logo(monkeypatch, heart),
        "extra_items": [{"id": "default-logo", "type": "image", "image_url": _old_embedded_logo(monkeypatch, coral), "asset": "coral"}],
    }
    asyncio.run(db.albums.update_one({"id": album_id}, {"$set": {"cover": old_cover, "updated_at": "2026-01-01T00:00:00+00:00"}}))

    got = client.get(f"/api/albums/{album_id}", headers=headers).json()
    assert got["cover"]["extra_items"][0]["image_url"] == coral
    assert got["cover"]["spine_logo_image"] == heart
    stored = asyncio.run(db.albums.find_one({"id": album_id}))
    assert stored["cover"]["extra_items"][0]["image_url"] == coral
    assert stored["updated_at"] == "2026-01-01T00:00:00+00:00"  # not an edit

    # A save from a page still showing the old copy is slimmed too.
    client.patch(f"/api/albums/{album_id}", json={"cover": old_cover}, headers=headers)
    stored = asyncio.run(db.albums.find_one({"id": album_id}))
    assert stored["cover"]["spine_logo_image"] == heart
