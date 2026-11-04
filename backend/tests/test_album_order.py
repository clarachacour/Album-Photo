"""The order photos go on the album's pages: by place when there's enough
GPS, a dated photo without GPS at its date (not pushed to the end)."""
BEIRUT = (33.89, 35.50)
LARNACA = (34.92, 33.63)


def _p(pid, when=None, where=None):
    lat, lng = where or (None, None)
    return {"id": pid, "taken_at": when, "gps_lat": lat, "gps_lng": lng}


def _ids(photos):
    # Imported here, like the other tests: the app's modules load once the
    # test database is in place (see conftest).
    from app.services.curation import order_for_album

    return [p["id"] for p in order_for_album(photos)]


def test_a_photo_without_gps_taken_first_opens_the_album():
    photos = [
        _p("beirut-1", "2026-07-01T10:00:00", BEIRUT), _p("beirut-2", "2026-07-01T11:00:00", BEIRUT),
        _p("larnaca-1", "2026-07-02T18:00:00", LARNACA), _p("larnaca-2", "2026-07-02T19:00:00", LARNACA),
        _p("airport", "2026-07-01T06:00:00"),  # indoors, no GPS, the trip's first photo
    ]
    assert _ids(photos) == ["airport", "beirut-1", "beirut-2", "larnaca-1", "larnaca-2"]


def test_a_photo_without_gps_joins_the_place_of_its_time():
    photos = [
        _p("beirut-1", "2026-07-01T10:00:00", BEIRUT), _p("beirut-2", "2026-07-01T12:00:00", BEIRUT),
        _p("larnaca-1", "2026-07-02T18:00:00", LARNACA), _p("larnaca-2", "2026-07-02T20:00:00", LARNACA),
        _p("dinner", "2026-07-02T19:00:00"),  # received on WhatsApp, during the evening in Larnaca
        _p("ferry", "2026-07-02T08:00:00"),  # between the two places
    ]
    assert _ids(photos) == ["beirut-1", "beirut-2", "ferry", "larnaca-1", "dinner", "larnaca-2"]


def test_photos_with_neither_date_nor_gps_go_last():
    photos = [_p("b1", "2026-07-01T10:00:00", BEIRUT), _p("b2", "2026-07-01T11:00:00", BEIRUT), _p("scan")]
    assert _ids(photos) == ["b1", "b2", "scan"]


def test_without_enough_gps_the_album_follows_the_dates():
    photos = [_p("c", "2026-07-03T10:00:00"), _p("a", "2026-07-01T10:00:00", BEIRUT), _p("b", "2026-07-02T10:00:00")]
    assert _ids(photos) == ["a", "b", "c"]
