"""Unit tests for small pure functions (no app startup needed)."""
import pytest

from app.core.signed_links import sign_order_action, verify_order_action
from app.services.pricing import (
    ORDER_PRICE_CENTS,
    OVERAGE_PER_PAGE_CENTS,
    compute_order_price_cents,
)


# ---------- Pricing ----------
@pytest.mark.parametrize("size", ["A4", "A5"])
def test_tier_prices_are_used_as_is(size):
    for pages, cents in ORDER_PRICE_CENTS[size].items():
        assert compute_order_price_cents(size, pages) == cents


def test_a_page_count_between_tiers_is_billed_as_the_next_tier():
    assert compute_order_price_cents("A4", 15) == ORDER_PRICE_CENTS["A4"][24]  # 24 is the minimum
    assert compute_order_price_cents("A4", 35) == ORDER_PRICE_CENTS["A4"][50]
    assert compute_order_price_cents("A5", 51) == ORDER_PRICE_CENTS["A5"][100]


def test_past_the_largest_tier_each_page_is_added():
    expected = ORDER_PRICE_CENTS["A4"][200] + 10 * OVERAGE_PER_PAGE_CENTS["A4"]
    assert compute_order_price_cents("A4", 210) == expected


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
def test_google_keys_are_downloaded_once_and_again_after_a_key_change(monkeypatch):
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


def test_brightness_tells_a_dark_photo_from_a_light_one():
    from app.services.curation import compute_brightness

    dark, light = compute_brightness(_jpeg((25, 22, 20))), compute_brightness(_jpeg((150, 140, 130)))
    assert dark["brightness"] < 0.2 < light["brightness"]
    assert dark["highlights"] < light["highlights"]
    assert compute_brightness(b"not an image") is None
