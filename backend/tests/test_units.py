"""Unit tests for small pure functions (no app startup needed)."""
import pytest

from app.core.signed_links import sign_order_action, verify_order_action
from app.services.pricing import (
    DIGITAL_PRICE_CENTS,
    ORDER_PRICE_CENTS,
    billed_tier,
    compute_digital_price_cents,
    compute_order_price_cents,
)


# ---------- Pricing ----------
@pytest.mark.parametrize("size", ["A4", "A5"])
def test_tier_prices_are_used_as_is(size):
    for pages, cents in ORDER_PRICE_CENTS[size].items():
        assert compute_order_price_cents(size, pages) == cents


def test_a_page_count_between_tiers_is_priced_at_the_nearest_tier():
    # As the printer bills it, up to 100 pages: 15 → 24, 28 → 24, 40 → 50.
    assert compute_order_price_cents("A4", 15) == ORDER_PRICE_CENTS["A4"][24]
    assert compute_order_price_cents("A4", 28) == ORDER_PRICE_CENTS["A4"][24]
    assert compute_order_price_cents("A4", 40) == ORDER_PRICE_CENTS["A4"][50]
    assert compute_order_price_cents("A5", 60) == ORDER_PRICE_CENTS["A5"][50]
    assert compute_order_price_cents("A5", 80) == ORDER_PRICE_CENTS["A5"][100]


def test_past_100_pages_each_extra_page_is_45_cents():
    assert compute_order_price_cents("A4", 120) == 9900 + 20 * 45
    assert compute_order_price_cents("A5", 101) == 8300 + 45
    assert compute_order_price_cents("A4", 149) == 9900 + 49 * 45
    assert compute_order_price_cents("A4", 150) == 12900
    assert compute_order_price_cents("A5", 160) == 11300 + 10 * 45


def test_halfway_between_two_tiers_the_tier_above():
    assert [billed_tier(p) for p in (36, 37, 74, 75)] == [24, 50, 50, 100]


def test_the_pdf_has_one_price():
    assert DIGITAL_PRICE_CENTS == 2200
    assert compute_digital_price_cents("A5", 24) == compute_digital_price_cents("A4", 150) == 2200


def test_the_price_list():
    assert ORDER_PRICE_CENTS["A4"] == {24: 5300, 50: 7300, 100: 9900, 150: 12900}
    assert ORDER_PRICE_CENTS["A5"] == {24: 4300, 50: 6300, 100: 8300, 150: 11300}


def test_unknown_size_is_priced_as_a4():
    assert compute_order_price_cents("A3", 24) == ORDER_PRICE_CENTS["A4"][24]


# ---------- Signed printer links ----------
def test_signed_link_round_trip():
    token = sign_order_action("order-1", "download")
    assert verify_order_action("order-1", "download", token)


def test_signed_link_cannot_be_reused_elsewhere():
    token = sign_order_action("order-1", "download")
    assert not verify_order_action("order-2", "download", token)  # other order
    assert not verify_order_action("order-1", "ready", token)  # other action
    assert not verify_order_action("order-1", "download", None)  # no token
    assert not verify_order_action("order-1", "download", token + "x")  # tampered


# ---------- PDF fonts ----------
def test_half_written_font_file_is_repaired(tmp_path):
    """A font file left incomplete (another process still writing it, or a
    crash mid-write) used to make the whole app fail to start."""
    import os
    import subprocess
    import sys

    font_dir = tmp_path / "albumai_fonts"
    font_dir.mkdir()
    (font_dir / "CormorantGaramond-Bold.ttf").write_bytes(b"\x00\x01")
    # tempfile.gettempdir() follows TMPDIR, so the app uses tmp_path.
    env = {**os.environ, "TMPDIR": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, "-c", "import app.services.pdf"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


# ---------- Google sign-in ----------
def test_google_keys_are_downloaded_once_and_again_after_a_key_change(app, monkeypatch):
    from app.core import auth

    downloads = []
    fresh = auth._CachedGoogleRequest()
    monkeypatch.setattr(auth, "_google_request", fresh)
    monkeypatch.setattr(
        auth.google_requests.Request,
        "__call__",
        lambda self, url, method="GET", **kw: downloads.append(url) or type("R", (), {"status": 200, "data": b"{}"})(),
    )

    def verify(token, request, audience):
        request("https://www.googleapis.com/oauth2/v1/certs")
        if token == "signed-with-new-key" and len(downloads) < 2:
            raise ValueError("Certificate for key id not found")
        return {"email": "a@b.c"}

    monkeypatch.setattr(auth.google_id_token, "verify_oauth2_token", verify)
    auth.verify_google_token("t1", "client")
    auth.verify_google_token("t2", "client")
    assert len(downloads) == 1  # kept between sign-ins
    assert auth.verify_google_token("signed-with-new-key", "client") == {"email": "a@b.c"}
    assert len(downloads) == 2  # fetched again once, not on every attempt


# ---------- Photo brightness ----------
def _jpeg(color):
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    img = Image.new("RGB", (400, 300), color)
    img.paste((255, 240, 200), (0, 0, 400, 20))  # a thin strip of bright sky
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_brightness_tells_a_dark_photo_from_a_light_one(app):
    from app.services.curation import compute_brightness

    dark, light = compute_brightness(_jpeg((25, 22, 20))), compute_brightness(_jpeg((150, 140, 130)))
    assert dark["brightness"] < 0.2 < light["brightness"]
    assert dark["highlights"] < light["highlights"]
    assert compute_brightness(b"not an image") is None


def test_an_album_opened_in_the_editor_gets_its_old_photos_measured(client, db, monkeypatch):
    """Photos uploaded before brightness was measured are measured when
    their album is opened and still editable — never an ordered album's."""
    import asyncio

    from app.services import photos
    from tests.test_api import _signup

    def measure(photo):
        if photo["id"].endswith("broken"):
            raise FileNotFoundError("not in R2")
        return {"brightness": 0.5, "highlights": 0.8}

    monkeypatch.setattr(photos, "_brightness_of_stored", measure)
    _, headers = _signup(client, db=db)
    editing = client.post("/api/albums", json={"title": "Draft"}, headers=headers).json()["id"]
    ordered = client.post("/api/albums", json={"title": "Done"}, headers=headers).json()["id"]
    asyncio.run(db.orders.insert_one({"id": "o-measure", "album_id": ordered, "kind": "print"}))
    for album_id in (editing, ordered):
        asyncio.run(db.photos.insert_many([
            {"id": f"{album_id}-ok", "album_id": album_id, "is_deleted": False, "storage_path": "a.jpg"},
            {"id": f"{album_id}-broken", "album_id": album_id, "is_deleted": False, "storage_path": "b.jpg"},
        ]))

    for album_id in (editing, ordered):
        client.get(f"/api/albums/{album_id}", headers=headers)
    assert asyncio.run(photos.measure_missing_brightness(editing, [f"{editing}-ok"])) == 0  # already done
    found = {p["id"]: p for p in client.get(f"/api/albums/{editing}", headers=headers).json()["photos"]}
    assert found[f"{editing}-ok"]["brightness"] == 0.5
    assert found[f"{editing}-broken"]["brightness"] is None  # unreadable: not tried again
    untouched = client.get(f"/api/albums/{ordered}", headers=headers).json()["photos"]
    assert all("brightness" not in p for p in untouched)
