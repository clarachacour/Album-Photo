"""Which photo is kept out of a moment: people first (an evening on a terrace
beats a sharp plate), the light and sharpness weighed against the moment's
other photos only — a sunset or an underwater photo, naturally soft, is
never left out for it — and still one photo per burst."""
import asyncio
import io
import random

from PIL import Image, ImageDraw


def _scene(seed, shift=0):
    """A photo of its own (seed), or the same one a step aside (shift)."""
    rnd = random.Random(seed)
    img = Image.new("RGB", (300, 400), tuple(rnd.randrange(256) for _ in range(3)))
    draw = ImageDraw.Draw(img)
    for _ in range(12):
        x, y = rnd.randrange(260), rnd.randrange(360)
        draw.rectangle((x + shift, y, x + shift + 40, y + 40), fill=tuple(rnd.randrange(256) for _ in range(3)))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def _photo(pid, data, taken_at, brightness=0.5):
    return {"id": pid, "album_id": "a", "storage_path": f"{pid}.jpg", "thumbnail_path": None, "taken_at": taken_at,
            "gps_lat": None, "gps_lng": None, "brightness": brightness, "_bytes": data}


def _curate(db, monkeypatch, photos, sharpness, faces):
    """Runs the curation with each photo's sharpness and faces given."""
    from app.services import curation

    for p in photos:
        p["phash"] = curation.ahash_to_str(curation.compute_ahash(p["_bytes"]))
        p["visual_signature"] = curation.compute_visual_signature(p["_bytes"])
    by_bytes = {p["_bytes"]: p["id"] for p in photos}
    data = {p["storage_path"]: p.pop("_bytes") for p in photos}
    asyncio.run(db.photos.insert_many([dict(p) for p in photos]))
    monkeypatch.setattr(curation, "GEMINI_API_KEY", None)
    monkeypatch.setattr(curation, "get_object", lambda path: (data[path], "image/jpeg"))
    monkeypatch.setattr(curation, "compute_sharpness", lambda b: sharpness[by_bytes[b]])
    monkeypatch.setattr(curation, "detect_faces", lambda b: faces.get(by_bytes[b], {"focal": None, "count": 0, "area": 0.0}))
    selected, _ = asyncio.run(curation.curate_photos(photos))
    return [p["id"] for p in selected]


FACE = {"focal": (0.5, 0.4), "count": 1, "area": 0.03}


def test_people_on_a_dark_terrace_beat_a_sharp_plate_in_the_same_moment():
    from app.services.curation import best_photo

    plate = {"id": "plate", "ai_score": 900.0, "brightness": 0.45, "ai_face_count": 0}
    friends = {"id": "friends", "ai_score": 60.0, "brightness": 0.18, "ai_face_count": 2, "ai_face_area": 0.02}
    assert best_photo([plate, friends])["id"] == "friends"


def test_among_photos_of_the_same_people_the_better_lit_and_sharper_wins():
    from app.services.curation import best_photo

    dark_blurry = {"id": "a", "ai_score": 20.0, "brightness": 0.1, "ai_face_count": 1, "ai_face_area": 0.03}
    good = {"id": "b", "ai_score": 80.0, "brightness": 0.3, "ai_face_count": 1, "ai_face_area": 0.03}
    assert best_photo([dark_blurry, good])["id"] == "b"


def test_a_burst_keeps_one_photo_the_one_with_the_people(app, db, monkeypatch):
    shots = [_photo(f"b{i}", _scene(1, shift=i * 2), f"2026-08-02T21:10:0{i}", brightness=0.2) for i in range(3)]
    sharpness = {"b0": 400.0, "b1": 90.0, "b2": 380.0}  # b1: softer, but she's in it
    kept = _curate(db, monkeypatch, shots, sharpness, {"b1": FACE})
    assert kept == ["b1"]


def test_soft_photos_that_are_fine_are_no_longer_left_out(app, db, monkeypatch):
    photos = [
        _photo("evening", _scene(2), "2026-08-02T21:30:00", brightness=0.16),  # people, at night
        _photo("sunset", _scene(3), "2026-08-02T19:40:00", brightness=0.35),  # smooth sky
        _photo("underwater", _scene(4), "2026-08-03T11:00:00", brightness=0.4),  # blue, soft
        _photo("plate", _scene(5), "2026-08-02T21:00:00", brightness=0.5),
    ]
    sharpness = {"evening": 2.5, "sunset": 5.0, "underwater": 6.0, "plate": 900.0}
    kept = _curate(db, monkeypatch, photos, sharpness, {"evening": FACE})
    assert sorted(kept) == ["evening", "plate", "sunset", "underwater"]


def test_a_really_failed_shot_is_still_left_out(app, db, monkeypatch):
    photos = [_photo("pocket", _scene(6), "2026-08-02T10:00:00", brightness=0.02), _photo("view", _scene(7), "2026-08-02T11:00:00")]
    kept = _curate(db, monkeypatch, photos, {"pocket": 0.8, "view": 300.0}, {})
    assert kept == ["view"]
