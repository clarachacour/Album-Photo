"""Order prices, computed server-side only."""



# Fixed page-count tiers the user picks from at album creation. A "custom"
# page count (not one of these) is priced at the nearest lower tier plus a
# per-page surcharge — see compute_order_price_cents.
PAGE_TIERS = [24, 50, 100, 150, 250]

# Price by format AND page tier, in cents — server-side only, the client
# never gets to set its own price. These are PLACEHOLDER values (Clara
# hasn't finalized real pricing with the printer yet) — adjust freely, this
# is the one place that needs to change once real prices are set.
# A3 removed — exceeds the printing office's max open (flat) hardcover size
# (70×33cm) in both orientations, so it was never actually printable.
ORDER_PRICE_CENTS = {
    "A5": {24: 2500, 50: 3500, 100: 5500, 150: 7500, 250: 11000},
    "A4": {24: 3500, 50: 4900, 100: 7900, 150: 10900, 250: 15900},
}

# Per extra page beyond the nearest lower tier, in cents — also a
# placeholder until real per-page economics are confirmed.
OVERAGE_PER_PAGE_CENTS = {"A5": 30, "A4": 45}

def compute_order_price_cents(size: str, target_pages: int) -> int:
    size = size if size in ORDER_PRICE_CENTS else "A4"
    tier_prices = ORDER_PRICE_CENTS[size]
    target_pages = max(1, int(target_pages or PAGE_TIERS[0]))
    if target_pages in tier_prices:
        return tier_prices[target_pages]
    lower_tiers = [t for t in PAGE_TIERS if t <= target_pages]
    base_tier = max(lower_tiers) if lower_tiers else min(PAGE_TIERS)
    extra_pages = max(0, target_pages - base_tier)
    return tier_prices[base_tier] + extra_pages * OVERAGE_PER_PAGE_CENTS[size]
