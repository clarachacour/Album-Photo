"""Duplicate detection: the photo as shown (camera orientation applied),
the finer visual signature, and the AI's "different photos" no longer
keeping two shots taken a minute apart."""
import asyncio
import io

from PIL import Image, ImageDraw, ImageEnhance


def _scene(seed=0, size=(1200, 900)):
    import random

    r = random.Random(seed)
    img = Image.new("RGB", size, (r.randint(60, 200), r.randint(60, 200), r.randint(60, 200)))
    draw = ImageDraw.Draw(img)
    for _ in range(25):
        x, y = r.randint(0, size[0] - 100), r.randint(0, size[1] - 100)
        draw.ellipse([x, y, x + r.randint(60, 300), y + r.randint(60, 300)], fill=(r.randint(0, 255), r.randint(0, 255), r.randint(0, 255)))
    return img


def _jpeg(img, orientation=None):
    buf = io.BytesIO()
    if orientation:
        exif = Image.Exif()
        exif[0x0112] = orientation
        img.save(buf, "JPEG", quality=90, exif=exif)
    else:
        img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def test_a_photo_and_its_copy_saved_turned_hash_alike(app):
    from app.services.curation import compute_ahash, compute_visual_signature, hamming_distance, visual_distance

    shown = _scene(1)
    # The camera stored it sideways with "turn 90°" in its EXIF; the copy
    # was saved already turned.
    stored_sideways = shown.rotate(90, expand=True)
    raw = _jpeg(stored_sideways, orientation=6)
    turned_copy = _jpeg(shown)
    assert hamming_distance(compute_ahash(raw), compute_ahash(turned_copy)) <= 4
    a = {"vsig": compute_visual_signature(raw)}
    b = {"vsig": compute_visual_signature(turned_copy)}
    assert visual_distance(a, b) <= 4


def test_the_signature_keeps_a_reframed_copy_close_and_different_photos_apart(app):
    from app.services.curation import compute_visual_signature, visual_distance

    base = _scene(2)
    shifted = ImageEnhance.Brightness(base.crop((60, 0, 1200, 900)).resize((1200, 900))).enhance(1.05)
    sig = lambda img: {"vsig": compute_visual_signature(_jpeg(img))}
    assert visual_distance(sig(base), sig(shifted)) <= 11
    for other in range(3, 13):
        assert visual_distance(sig(base), sig(_scene(other))) > 16


def test_without_signatures_the_ahash_is_used(app):
    from app.services.curation import visual_distance

    assert visual_distance({"phash": "ffffffffffffffff"}, {"phash": "fffffffffffffff0"}) == 4
    assert visual_distance({"phash": "ffffffffffffffff", "vsig": None}, {"phash": "ffffffffffffffff"}) == 0


def _photo(i, when, shift):
    img = Image.new("RGB", (300, 400), (20, 30, 25))
    draw = ImageDraw.Draw(img)
    for r in range(40, 300, 40):
        draw.arc((150 - r, 60 - r // 2, 150 + r, 60 + r * 2), 180, 360, fill=(240, 240, 230), width=6)
    draw.rectangle((120 + shift, 220, 150 + shift, 380), fill=(70, 90, 60))
    return {
        "id": f"m{i}", "album_id": "a", "storage_path": f"m{i}.jpg", "thumbnail_path": None,
        "taken_at": when, "gps_lat": None, "gps_lng": None, "_bytes": _jpeg(img),
    }


def test_shots_a_minute_apart_stay_one_moment_even_if_the_ai_splits_them(app, db, monkeypatch):
    from app.services import curation

    # 30 s apart: not a burst (20 s), so the AI is asked — and calls them
    # different. Looking this alike, a minute apart, they're one moment.
    photos = [_photo(0, "2025-05-13T23:47:00", 0), _photo(1, "2025-05-13T23:47:30", 40)]
    for p in photos:
        p["phash"] = curation.ahash_to_str(curation.compute_ahash(p["_bytes"]))
    data = {p["storage_path"]: p.pop("_bytes") for p in photos}
    asyncio.run(db.photos.delete_many({"id": {"$in": [p["id"] for p in photos]}}))  # left by another test
    asyncio.run(db.photos.insert_many([dict(p) for p in photos]))

    async def split_everything(cluster):
        return [[p] for p in cluster]

    monkeypatch.setattr(curation, "GEMINI_API_KEY", "key")
    monkeypatch.setattr(curation, "_resolve_ambiguous_cluster_with_ai", split_everything)
    monkeypatch.setattr(curation, "get_object", lambda path: (data[path], "image/jpeg"))

    selected, stats = asyncio.run(curation.curate_photos(photos))
    assert stats["ai_calls_attempted"] == 1
    assert len(selected) == 1


def test_the_ai_split_still_holds_for_photos_taken_further_apart(app, db, monkeypatch):
    from app.services import curation

    photos = [_photo(0, "2025-05-13T23:40:00", 0), _photo(1, "2025-05-13T23:43:00", 40)]
    for p in photos:
        p["phash"] = curation.ahash_to_str(curation.compute_ahash(p["_bytes"]))
    data = {p["storage_path"]: p.pop("_bytes") for p in photos}
    asyncio.run(db.photos.delete_many({"id": {"$in": [p["id"] for p in photos]}}))  # left by another test
    asyncio.run(db.photos.insert_many([dict(p) for p in photos]))

    async def split_everything(cluster):
        return [[p] for p in cluster]

    monkeypatch.setattr(curation, "GEMINI_API_KEY", "key")
    monkeypatch.setattr(curation, "_resolve_ambiguous_cluster_with_ai", split_everything)
    monkeypatch.setattr(curation, "get_object", lambda path: (data[path], "image/jpeg"))

    selected, _ = asyncio.run(curation.curate_photos(photos))
    assert len(selected) == 2
