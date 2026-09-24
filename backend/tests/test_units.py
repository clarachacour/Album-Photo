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


def test_custom_page_count_adds_overage_to_lower_tier():
    expected = ORDER_PRICE_CENTS["A4"][50] + 10 * OVERAGE_PER_PAGE_CENTS["A4"]
    assert compute_order_price_cents("A4", 60) == expected


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
