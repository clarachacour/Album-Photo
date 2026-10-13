// Kept in sync with the backend's ORDER_PRICE_CENTS / compute_order_price_cents
// — shown here for live price previews (while choosing a page count during
// album creation, and again in the order summary); the backend always
// recomputes and owns the real charged price.
//
// Single shared source for both CreateAlbum.jsx (StepFormat, so the person
// can see what they'll pay while they're still choosing) and
// OrderCheckoutPage.jsx — previously each page kept its own copy of this
// table, which is exactly the kind of duplication that quietly drifts out
// of sync.

// Test week: prices are shown as usual, but the album is offered when
// ordering — only delivery is due, in cash to the courier. Set back to false
// to charge albums again. Keep in sync with FREE_TRIAL in
// backend/app/services/pricing.py (which charges).
export const FREE_TRIAL = true;

export const PAGE_TIERS = [24, 50, 100, 150, 200];

export const PRICE_TABLE = {
  A5: { 24: 25, 50: 35, 100: 55, 150: 75, 200: 92 },
  A4: { 24: 35, 50: 49, 100: 79, 150: 109, 200: 134 },
};

export const OVERAGE_PER_PAGE = { A5: 0.3, A4: 0.45 };

// The tier an album of pageCount pages is billed as (billed_tier in the
// backend): the smallest one that holds it (24 at least: 15 pages → 24,
// 35 → 50); past the largest, the page count itself.
export function billedTier(pageCount) {
  const pages = Math.max(1, Number(pageCount) || PAGE_TIERS[0]);
  return PAGE_TIERS.find((t) => t >= pages) ?? pages;
}

// The album's price (shown); freeTrial: what is due for it during the test week (0).
export function computeUnitPrice(size, pageCount, freeTrial = false) {
  if (freeTrial) return 0;
  const tierPrices = PRICE_TABLE[size] || PRICE_TABLE.A4;
  const tier = billedTier(pageCount);
  if (tierPrices[tier] != null) return tierPrices[tier];
  const largest = PAGE_TIERS[PAGE_TIERS.length - 1];
  return tierPrices[largest] + (tier - largest) * (OVERAGE_PER_PAGE[size] || OVERAGE_PER_PAGE.A4);
}

// Mirrors billed_page_count in backend/app/services/pricing.py: the album's
// real page count (the chosen one only while it has no pages yet).
export function billedPageCount(album) {
  return (album?.pages || []).length || Number(album?.target_pages) || PAGE_TIERS[0];
}

// A digital album (the PDF to download) costs the printed album's price
// minus this — keep in sync with DIGITAL_DISCOUNT_CENTS in
// backend/app/services/pricing.py, which charges it.
export const DIGITAL_DISCOUNT = 15;

export function computeDigitalPrice(size, pageCount, freeTrial = false) {
  return Math.max(0, computeUnitPrice(size, pageCount, freeTrial) - DIGITAL_DISCOUNT);
}

// Delivery (Lebanon only), per order — keep in sync with SHIPPING_PRICE_CENTS
// in backend/app/services/pricing.py, which charges it.
export const SHIPPING_PRICE = 5;

// Version of the terms of sale shown on the site (their "last updated"
// date). Sent with an order when the customer ticks "I accept"; must match
// TERMS_VERSION in backend/app/services/pricing.py.
export const TERMS_VERSION = "2026-10-11";

// What the customer pays for an order, in cents: its total — but during the
// test week only the delivery (nothing for a PDF), even for an order placed
// before it (same as cash_due in backend/app/services/wakilni.py).
export function amountDueCents(order) {
  if (!FREE_TRIAL) return order?.total_price_cents || 0;
  if (order?.kind === "digital") return 0;
  return order?.shipping_price_cents ?? SHIPPING_PRICE * 100;
}
