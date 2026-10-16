"""Order prices, computed server-side only."""



# Fixed page-count tiers the user picks from at album creation. An album is
# billed at the smallest tier that holds its real page count (15 pages → 24,
# 35 → 50); beyond the largest tier, a per-page surcharge is added — see
# compute_order_price_cents.
PAGE_TIERS = [24, 50, 100, 150]

# Test week: every album is free — only delivery is due, in cash to the
# courier. Set back to False to charge albums again. Keep in sync with
# FREE_TRIAL in frontend/src/lib/pricing.js (which hides the prices).
FREE_TRIAL = True

# Price by format AND page tier, in cents — server-side only, the client
# never gets to set its own price. An album between two tiers pays the
# tier above (35 pages → the 50-page price); 150 pages at most.
# A3 removed — exceeds the printing office's max open (flat) hardcover size
# (70×33cm) in both orientations, so it was never actually printable.
ORDER_PRICE_CENTS = {
    "A5": {24: 4300, 50: 6300, 100: 8300, 150: 11300},
    "A4": {24: 5300, 50: 7300, 100: 9900, 150: 12900},
}

# A digital album (the PDF to download, no printing or delivery): one
# fixed price whatever its format and page count, in cents. Keep in sync
# with DIGITAL_PRICE in frontend/src/lib/pricing.js.
DIGITAL_PRICE_CENTS = 2500

# Delivery (Lebanon only), per order, in cents. Shown at checkout — keep in
# sync with SHIPPING_PRICE in frontend/src/lib/pricing.js.
SHIPPING_PRICE_CENTS = 500

# The version of the terms of sale the site shows (the "last updated" date
# of legal.terms in the locale files). An order records the one the
# customer accepted; change both together when the terms change.
TERMS_VERSION = "2026-10-16"

# Per extra page beyond the largest tier, in cents — also a placeholder
# until real per-page economics are confirmed.
OVERAGE_PER_PAGE_CENTS = {"A5": 30, "A4": 45}

def billed_page_count(album: dict) -> int:
    """Pages the order is charged for: the album's real page count (the
    page count chosen at creation only when there are no pages yet). It
    can't be set by the client: a 250-page album was once ordered at the
    24-page price by lowering the chosen count."""
    pages = len(album.get("pages") or [])
    return pages or int(album.get("target_pages") or PAGE_TIERS[0])


def billed_tier(page_count: int) -> int:
    """The tier an album of page_count pages is billed as: the smallest one
    that holds it (24 at least); past the largest, the page count itself."""
    page_count = max(1, int(page_count or PAGE_TIERS[0]))
    return next((t for t in PAGE_TIERS if t >= page_count), page_count)


def compute_order_price_cents(size: str, page_count: int) -> int:
    if FREE_TRIAL:
        return 0
    size = size if size in ORDER_PRICE_CENTS else "A4"
    tier_prices = ORDER_PRICE_CENTS[size]
    tier = billed_tier(page_count)
    if tier in tier_prices:
        return tier_prices[tier]
    largest = PAGE_TIERS[-1]
    return tier_prices[largest] + (tier - largest) * OVERAGE_PER_PAGE_CENTS[size]


def compute_digital_price_cents(size: str, page_count: int) -> int:
    """A digital album's price: DIGITAL_PRICE_CENTS, whatever the album."""
    return 0 if FREE_TRIAL else DIGITAL_PRICE_CENTS
