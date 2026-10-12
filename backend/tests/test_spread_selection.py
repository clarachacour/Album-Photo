from app.services.curation import spread_to_capacity


def photo(pid, minute, phash, score=10.0):
    return {"id": pid, "taken_at": f"2025-07-01T10:{minute:02d}:00", "phash": phash, "ai_score": score}


def test_keeps_everything_when_it_fits():
    photos = [photo("a", 0, "0" * 16), photo("b", 30, "f" * 16)]
    kept, dropped = spread_to_capacity(photos, 5)
    assert kept == photos and dropped == []


def test_drops_look_alikes_first_and_keeps_the_end_of_the_album():
    burst = [photo(f"burst{i}", i, "0" * 15 + str(i), score=10 + i) for i in range(4)]  # same minute range, same look
    later = [photo("lake", 40, "f" * 16), photo("dinner", 55, "0f" * 8)]
    kept, dropped = spread_to_capacity(burst + later, 3)
    ids = [p["id"] for p in kept]
    assert "lake" in ids and "dinner" in ids  # the end of the day isn't cut
    assert sum(1 for i in ids if i.startswith("burst")) == 1  # one shot of the burst
    assert ids == [p["id"] for p in burst + later if p["id"] in ids]  # album order kept
    assert len(dropped) == 3


def test_keeps_the_sharper_of_two_look_alikes():
    a, b = photo("soft", 0, "0" * 16, score=5), photo("sharp", 1, "0" * 16, score=50)
    kept, _ = spread_to_capacity([a, b, photo("other", 50, "f" * 16)], 2)
    assert [p["id"] for p in kept] == ["sharp", "other"]
