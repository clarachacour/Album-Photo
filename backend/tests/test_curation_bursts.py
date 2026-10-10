"""Photos shot one after another (a burst) are one moment: only one is kept,
even when the AI would call a slightly different pose a different photo."""
import asyncio
import io

from PIL import Image, ImageDraw


def _photo(i, second, shift):
    img = Image.new("RGB", (300, 400), (20, 30, 25))
    draw = ImageDraw.Draw(img)
    for r in range(40, 300, 40):
        draw.arc((150 - r, 60 - r // 2, 150 + r, 60 + r * 2), 180, 360, fill=(240, 240, 230), width=6)
    draw.rectangle((120 + shift, 220, 150 + shift, 380), fill=(70, 90, 60))  # the person, a step aside
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return {
        "id": f"p{i}", "album_id": "a", "storage_path": f"p{i}.jpg", "thumbnail_path": None,
        "taken_at": f"2025-05-13T23:47:4{second}", "gps_lat": None, "gps_lng": None,
        "_bytes": buf.getvalue(),
    }


def test_a_burst_keeps_one_photo_even_if_the_ai_would_split_it(app, db, monkeypatch):
    from app.services import curation

    # The person moves enough for the hashes to differ (distance 8): too far
    # apart to skip the AI on looks alone, close enough to be one burst.
    photos = [_photo(0, 2, 0), _photo(1, 3, 40), _photo(2, 4, 80)]
    for p in photos:
        p["phash"] = curation.ahash_to_str(curation.compute_ahash(p["_bytes"]))
    data = {p["storage_path"]: p.pop("_bytes") for p in photos}
    asyncio.run(db.photos.insert_many([dict(p) for p in photos]))

    async def split_everything(cluster):
        return [[p] for p in cluster]

    monkeypatch.setattr(curation, "GEMINI_API_KEY", "key")
    monkeypatch.setattr(curation, "_resolve_ambiguous_cluster_with_ai", split_everything)
    monkeypatch.setattr(curation, "get_object", lambda path: (data[path], "image/jpeg"))

    selected, stats = asyncio.run(curation.curate_photos(photos))
    assert len(selected) == 1
    assert stats["ai_calls_attempted"] == 0
