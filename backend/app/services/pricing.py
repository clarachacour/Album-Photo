"""Order prices, computed server-side only."""



# Fixed page-count tiers the user picks from at album creation. An album is
# priced at the nearest tier to its real page count (15 pages → 24, 28 → 24,
# 40 → 50, 160 → 150) — the printer bills us the same way. Halfway between
# two tiers (37, 75, 125 pages), the tier above.
PAGE_TIERS = [24, 50, 100, 150]

# Test week: every album is free — only delivery is due, in cash to the
# courier. Set to True to offer albums again. Keep in sync with FREE_TRIAL
# in frontend/src/lib/pricing.js (which hides the prices).
FREE_TRIAL = False

# Orders placed before the test week (which started on 2026-10-13) had the
# album's price in their total, but were offered too: only the delivery is
# collected for them. Keep in sync with OFFERED_BEFORE in
# frontend/src/lib/pricing.js.
OFFERED_BEFORE = "2026-10-14T00:00:00+00:00"


def album_offered(order: dict) -> bool:
    """Whether the album itself is free for this order (only the delivery
    is due): during the test week, for an order placed at 0 for the album,
    or for one placed before the test week."""
    if FREE_TRIAL or int(order.get("unit_price_cents") or 0) == 0:
        return True
    created = order.get("created_at")
    return bool(created) and str(created) < OFFERED_BEFORE

# Price by format AND page tier, in cents — server-side only, the client
# never gets to set its own price. An album between two tiers pays the
# nearest one, or past 100 pages a price per extra page (see priced_pages).
# A3 removed — exceeds the printing office's max open (flat) hardcover size
# (70×33cm) in both orientations, so it was never actually printable.
ORDER_PRICE_CENTS = {
    "A5": {24: 4300, 50: 6300, 100: 8300, 150: 11300},
    "A4": {24: 5300, 50: 7300, 100: 9900, 150: 12900},
}

# A digital album (the PDF to download, no printing or delivery): one
# fixed price whatever its format and page count, in cents. Keep in sync
# with DIGITAL_PRICE in frontend/src/lib/pricing.js.
DIGITAL_PRICE_CENTS = 2200

# Delivery (Lebanon only), per order, in cents. Shown at checkout — keep in
# sync with SHIPPING_PRICE in frontend/src/lib/pricing.js.
SHIPPING_PRICE_CENTS = 500

# The version of the terms of sale the site shows (the "last updated" date
# of legal.terms in the locale files). An order records the one the
# customer accepted; change both together when the terms change.
TERMS_VERSION = "2026-10-29"

# Past OVERAGE_FROM pages, an album pays its tier's price plus this much
# per page beyond it, in cents, whatever its format (see priced_pages):
# the grid's own step from 100 to 150 pages ($30 over 50 pages, in A4 and
# A5), so a 150-page album costs its tier's price either way.
# Keep in sync with OVERAGE_FROM / OVERAGE_PER_PAGE in
# frontend/src/lib/pricing.js.
OVERAGE_FROM = 100
OVERAGE_PER_PAGE_CENTS = 60


def billed_page_count(album: dict) -> int:
    """Pages the order is charged for: the album's real page count (the
    page count chosen at creation only when there are no pages yet). It
    can't be set by the client: a 250-page album was once ordered at the
    24-page price by lowering the chosen count."""
    pages = len(album.get("pages") or [])
    return pages or int(album.get("target_pages") or PAGE_TIERS[0])


def nearest_tier(page_count: int, tiers) -> int:
    """The tier nearest to page_count (the one above when halfway)."""
    pages = max(1, int(page_count or 0))
    return min(tiers, key=lambda t: (abs(t - pages), -t))


def priced_pages(page_count: int, tiers=PAGE_TIERS) -> tuple:
    """(tier, extra pages) an album of page_count pages is priced as. Up
    to OVERAGE_FROM pages, the nearest tier (15 → 24, 28 → 24, 40 → 50),
    with no extra page; past it, the largest tier it reaches, plus every
    page beyond it (120 → 100 + 20, 150 → 150 + 0, 160 → 150 + 10)."""
    pages = max(1, int(page_count or tiers[0]))
    if pages <= OVERAGE_FROM:
        return nearest_tier(pages, tiers), 0
    base = max(t for t in tiers if t <= pages)
    return base, pages - base


def billed_tier(page_count: int) -> int:
    """The tier an album of page_count pages is priced from (see priced_pages)."""
    return priced_pages(page_count)[0]


def compute_order_price_cents(size: str, page_count: int) -> int:
    if FREE_TRIAL:
        return 0
    size = size if size in ORDER_PRICE_CENTS else "A4"
    tier, extra = priced_pages(page_count)
    return ORDER_PRICE_CENTS[size][tier] + extra * OVERAGE_PER_PAGE_CENTS


def compute_digital_price_cents(size: str, page_count: int) -> int:
    """A digital album's price: DIGITAL_PRICE_CENTS, whatever the album."""
    return 0 if FREE_TRIAL else DIGITAL_PRICE_CENTS
