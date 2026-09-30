"""Direct links to photos in R2: signed exactly like boto3 would, stable
all day (so the browser cache works), and added to the album's photos."""
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from tests.test_api import _signup


@pytest.fixture()
def r2(app, monkeypatch):
    from app.services import signed_urls

    monkeypatch.setattr(signed_urls, "R2_ACCOUNT_ID", "acc123")
    monkeypatch.setattr(signed_urls, "R2_ACCESS_KEY_ID", "AKIDEXAMPLE")
    monkeypatch.setattr(signed_urls, "R2_SECRET_ACCESS_KEY", "secret/KEY+example")
    monkeypatch.setattr(signed_urls, "R2_BUCKET_NAME", "album-photo")
    signed_urls._key_cache.clear()
    return signed_urls


def test_same_signature_as_boto3(r2, monkeypatch):
    import boto3
    import botocore.auth
    from botocore.config import Config

    start = datetime(2026, 9, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(botocore.auth, "get_current_datetime", lambda: start.replace(tzinfo=None))
    client = boto3.client(
        "s3", endpoint_url="https://acc123.r2.cloudflarestorage.com", aws_access_key_id="AKIDEXAMPLE",
        aws_secret_access_key="secret/KEY+example", region_name="auto",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    path = "everbook/photos/ab c/été+1.jpg"
    expected = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": "album-photo", "Key": path, "ResponseCacheControl": r2.CACHE_CONTROL},
        ExpiresIn=int(r2.LINK_VALIDITY.total_seconds()),
    )
    mine = r2.signed_url(path, start)
    e, m = urlparse(expected), urlparse(mine)
    assert (m.netloc, m.path) == (e.netloc, e.path)
    assert parse_qs(m.query) == parse_qs(e.query)


def test_links_stay_the_same_all_day_and_last_at_least_6_days(r2):
    morning = r2.window_start(datetime(2026, 9, 30, 0, 5, tzinfo=timezone.utc))
    evening = r2.window_start(datetime(2026, 9, 30, 23, 55, tzinfo=timezone.utc))
    assert r2.signed_url("a/b.jpg", morning) == r2.signed_url("a/b.jpg", evening)
    assert r2.LINK_VALIDITY - timedelta(days=1) >= timedelta(days=6)


def test_fast_enough_for_a_big_album(r2):
    start = r2.window_start()
    t0 = time.perf_counter()
    for i in range(5000):
        r2.photo_urls({"thumbnail_path": f"t/{i}.jpg", "medium_path": f"m/{i}.jpg", "storage_path": f"o/{i}.jpg", "content_type": "image/jpeg"}, start)
    assert time.perf_counter() - t0 < 1.5


def test_sizes_not_made_yet_are_left_to_the_server(r2):
    urls = r2.photo_urls({"thumbnail_path": "t.jpg", "storage_path": "o.heic", "content_type": "image/heic"})
    assert set(urls) == {"thumb", "expires_at"}  # no medium yet, HEIC not converted yet


def test_album_photos_come_with_their_links(client, db, r2):
    import asyncio

    _, headers = _signup(client, db=db)
    album_id = client.post("/api/albums", json={"title": "T"}, headers=headers).json()["id"]
    from app.core.auth import decode_token

    user_id = decode_token(headers["Authorization"].split()[1])
    asyncio.run(db.photos.insert_one({"id": "p1", "album_id": album_id, "user_id": user_id, "is_deleted": False, "thumbnail_path": "x/p1_thumb.jpg", "storage_path": "x/p1.jpg", "content_type": "image/jpeg"}))
    photo = client.get(f"/api/albums/{album_id}", headers=headers).json()["photos"][0]
    assert photo["urls"]["thumb"].startswith("https://acc123.r2.cloudflarestorage.com/album-photo/x/p1_thumb.jpg?")
    assert "print" in photo["urls"] and "medium" not in photo["urls"]


def test_without_r2_no_links(client, db):
    from app.services import signed_urls

    assert signed_urls.photo_urls({"thumbnail_path": "t.jpg"}) is None
