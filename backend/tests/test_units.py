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
