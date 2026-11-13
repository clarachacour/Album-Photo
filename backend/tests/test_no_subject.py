"""Photos without a subject (the photographer's feet, the floor, a pocket,
a screenshot…) are set aside like blurry ones: Gemini names them; food,
landscapes and photos with people are never at risk; a failed or
suspicious answer keeps every photo."""
import asyncio
import json as jsonlib


class _Resp:
    def __init__(self, text):
        self._text = text

    def raise_for_status(self):
        pass

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": self._text}]}}]}


def _photos(n, faces=()):
    return [{"id": f"ns-{i}", "storage_path": f"p/{i}.jpg", "ai_face_count": 1 if i in faces else 0} for i in range(n)]


def _gemini(monkeypatch, answer, sent=None):
    from app.services import curation

    monkeypatch.setattr(curation, "GEMINI_API_KEY", "key")
    monkeypatch.setattr(curation, "get_object", lambda path: (b"jpeg", "image/jpeg"))

    def post(url, headers=None, json=None, timeout=None):
        parts = json["contents"][0]["parts"]
        if sent is not None:
            sent.append(len([p for p in parts if "inline_data" in p]))
        prompt = parts[-1]["text"]
        assert "NEVER list: food" in prompt and "landscapes" in prompt
        return _Resp(answer if isinstance(answer, str) else jsonlib.dumps(answer))

    monkeypatch.setattr(curation.requests, "post", post)
    return curation


def test_the_photos_gemini_names_are_found_and_people_are_never_asked_about(monkeypatch):
    sent = []
    curation = _gemini(monkeypatch, [1], sent)
    photos = _photos(5, faces={0})
    found = asyncio.run(curation.find_no_subject_photos(photos))
    # Photo 0 has a face: not sent. Of the 4 sent, Gemini's "1" is ns-2.
    assert sent == [4]
    assert found == {"ns-2"}


def test_a_suspicious_or_broken_answer_keeps_every_photo(monkeypatch):
    curation = _gemini(monkeypatch, [0, 1, 2])  # 3 of 4: more than 40%
    assert asyncio.run(curation.find_no_subject_photos(_photos(4))) == set()
    curation = _gemini(monkeypatch, "not json")
    assert asyncio.run(curation.find_no_subject_photos(_photos(4))) == set()
    curation = _gemini(monkeypatch, [9])  # a number that isn't a photo
    assert asyncio.run(curation.find_no_subject_photos(_photos(4))) == set()


def test_without_a_key_nothing_is_asked(monkeypatch):
    from app.services import curation

    monkeypatch.setattr(curation, "GEMINI_API_KEY", None)
    monkeypatch.setattr(curation.requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no call")))
    assert asyncio.run(curation.find_no_subject_photos(_photos(3))) == set()


def test_photos_are_sent_in_batches(monkeypatch):
    sent = []
    curation = _gemini(monkeypatch, [], sent)
    asyncio.run(curation.find_no_subject_photos(_photos(curation.NO_SUBJECT_BATCH + 3)))
    assert sorted(sent) == [3, curation.NO_SUBJECT_BATCH]


def test_curation_sets_the_photo_aside_and_says_so(app, db, monkeypatch):
    from app.services import curation
    from tests.test_curation_dedup import _jpeg, _scene

    photos = []
    data = {}
    for i in range(3):
        pid = f"ns-curate-{i}"
        path = f"albums/ns/{pid}.jpg"
        data[path] = _jpeg(_scene(seed=100 + i * 37))
        photos.append({"id": pid, "album_id": "ns", "user_id": "u", "storage_path": path, "taken_at": f"2025-06-0{i + 1}T12:00:00", "is_deleted": False})
    for p in photos:
        p["phash"] = curation.ahash_to_str(curation.compute_ahash(data[p["storage_path"]]))
    asyncio.run(db.photos.delete_many({"id": {"$in": [p["id"] for p in photos]}}))
    asyncio.run(db.photos.insert_many([dict(p) for p in photos]))
    monkeypatch.setattr(curation, "get_object", lambda path: (data[path], "image/jpeg"))

    async def feet(candidates):
        return {"ns-curate-1"}

    monkeypatch.setattr(curation, "find_no_subject_photos", feet)
    selected, stats = asyncio.run(curation.curate_photos(photos))
    assert [p["id"] for p in selected] == ["ns-curate-0", "ns-curate-2"]
    assert stats["no_subject_removed"] == 1
    stored = asyncio.run(db.photos.find_one({"id": "ns-curate-1"}, {"_id": 0}))
    # Set aside, not deleted: still among the album's photos.
    assert stored["ai_no_subject"] is True and stored["is_selected"] is False and not stored.get("is_deleted")
