def photo(pid, minute, phash, score=10.0):
    return {"id": pid, "taken_at": f"2025-07-01T10:{minute:02d}:00", "phash": phash, "ai_score": score}


def test_keeps_everything_when_it_fits(app):
    from app.services.curation import spread_to_capacity

    photos = [photo("a", 0, "0" * 16), photo("b", 30, "f" * 16)]
    kept, dropped = spread_to_capacity(photos, 5)
    assert kept == photos and dropped == []


def test_drops_look_alikes_first_and_keeps_the_end_of_the_album(app):
    from app.services.curation import spread_to_capacity

    burst = [photo(f"burst{i}", i, "0" * 15 + str(i), score=10 + i) for i in range(4)]  # same minute range, same look
    later = [photo("lake", 40, "f" * 16), photo("dinner", 55, "0f" * 8)]
    kept, dropped = spread_to_capacity(burst + later, 3)
    ids = [p["id"] for p in kept]
    assert "lake" in ids and "dinner" in ids  # the end of the day isn't cut
    assert sum(1 for i in ids if i.startswith("burst")) == 1  # one shot of the burst
    assert ids == [p["id"] for p in burst + later if p["id"] in ids]  # album order kept
    assert len(dropped) == 3


def test_keeps_the_sharper_of_two_look_alikes(app):
    from app.services.curation import spread_to_capacity

    a, b = photo("soft", 0, "0" * 16, score=5), photo("sharp", 1, "0" * 16, score=50)
    kept, _ = spread_to_capacity([a, b, photo("other", 50, "f" * 16)], 2)
    assert [p["id"] for p in kept] == ["sharp", "other"]


def test_same_result_as_the_simple_version(app):
    from app.services.curation import spread_to_capacity

    """The fast version (costs updated pair by pair) picks exactly what
    recomputing every pair each time would."""
    import random
    from app.services.curation import _redundancy

    def simple(photos, capacity):
        kept = list(photos)
        while len(kept) > capacity:
            costs = [_redundancy(kept[i], kept[i + 1]) for i in range(len(kept) - 1)]
            i = min(range(len(costs)), key=costs.__getitem__)
            a, b = kept[i], kept[i + 1]
            kept.pop(i if (a.get("ai_score") or 0) < (b.get("ai_score") or 0) else i + 1)
        return kept

    r = random.Random(7)
    photos = [photo(str(i), r.randrange(60), "%016x" % r.getrandbits(64), r.random()) for i in range(120)]
    photos.sort(key=lambda p: p["taken_at"])
    for cap in (1, 10, 60, 119):
        assert [p["id"] for p in spread_to_capacity(photos, cap)[0]] == [p["id"] for p in simple(photos, cap)]
