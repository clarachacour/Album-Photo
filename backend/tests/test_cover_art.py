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
    urls = {u for u in urls if "{" not in u}  # the v1 → v2 table is built from names
    assert len(urls) == 19
    for url in urls:
        assert (FRONTEND / "public" / url.lstrip("/")).is_file(), url


def test_old_small_spine_logo_is_recognised():
    old_mom = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADoAAAA4CAYAAACsc+sjAAAf+UlEQVR42j276Y4cWZqe+ZzVNt9iZwS3JJNLbrV0t9SNqdbM/BAwA93CYPRHlyDdQOuSNAIESQ2NegR0t4RqVWdVZW"
    assert slim_image(old_mom) == "/cover-art/mom-heart-logo-v1.webp"
    assert slim_image("data:image/png;base64,AAAA") == "data:image/png;base64,AAAA"  # someone's own image
    assert slim_image("https://example.com/x.png") == "https://example.com/x.png"


def test_redrawn_travel_icons_get_their_new_file():
    from app.services.cover_art import _REDRAWN

    assert slim_image("/cover-art/travel-sicily-v1.svg") == "/cover-art/travel-sicily-v2.svg"
    assert slim_image("/cover-art/travel-australia-v1.svg") == "/cover-art/travel-australia-v1.svg"  # already curves
    for old, new in _REDRAWN.items():
        assert (FRONTEND / "public" / old.lstrip("/")).is_file(), old  # kept: never changed in place
        assert (FRONTEND / "public" / new.lstrip("/")).is_file(), new
    # an album whose embedded copy was the old drawing goes straight to the new one
    from app.services import cover_art

    embedded = "data:image/svg+xml;base64,AAAA"
    cover_art._BY_HASH[hashlib.sha256(embedded.encode()).hexdigest()] = "/cover-art/travel-paros-v1.svg"
    try:
        assert slim_image(embedded) == "/cover-art/travel-paros-v2.svg"
    finally:
        del cover_art._BY_HASH[hashlib.sha256(embedded.encode()).hexdigest()]


def test_redrawn_svgs_are_smooth_curves():
    for path in (FRONTEND / "public" / "cover-art").glob("travel-*-v2.svg"):
        paths = re.findall(r' d="([^"]*)"', path.read_text())
        assert paths and all(" L" not in d and " C" in d for d in paths), path.name


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


def test_older_albums_get_the_redrawn_travel_icon_when_read(client, db):
    headers = _signup(client, db)
    album_id = client.post("/api/albums", json={"title": "Sicily"}, headers=headers).json()["id"]
    icon = {"id": "template-icon", "type": "image", "image_url": "/cover-art/travel-sicily-v1.svg", "asset": "travel_sicily"}
    asyncio.run(db.albums.update_one({"id": album_id}, {"$set": {"cover": {"extra_items": [icon]}}}))

    got = client.get(f"/api/albums/{album_id}", headers=headers).json()
    assert got["cover"]["extra_items"][0]["image_url"] == "/cover-art/travel-sicily-v2.svg"
    stored = asyncio.run(db.albums.find_one({"id": album_id}))
    assert stored["cover"]["extra_items"][0]["image_url"] == "/cover-art/travel-sicily-v2.svg"


def test_oldest_albums_get_the_vector_icon_from_its_tag():
    old_png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAOEAAAEWCAYAAACQU/BvAAD"
    cover = {"extra_items": [
        {"id": "a", "type": "image", "image_url": old_png, "asset": "travel_sicily"},
        {"id": "b", "type": "image", "image_url": old_png, "asset": "travel_australia"},
        {"id": "c", "type": "image", "image_url": old_png},  # someone's own picture: kept
    ]}
    slim, changed = slim_cover(cover)
    assert changed
    assert [i["image_url"] for i in slim["extra_items"]] == [
        "/cover-art/travel-sicily-v2.svg", "/cover-art/travel-australia-v1.svg", old_png,
    ]
