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
// ordering — only delivery is due, in cash to the courier. Set to true to
// offer albums again. Keep in sync with FREE_TRIAL in
// backend/app/services/pricing.py (which charges).
export const FREE_TRIAL = false;

// Orders placed before the test week were offered too (only the delivery is
// due) — same as OFFERED_BEFORE in backend/app/services/pricing.py.
export const OFFERED_BEFORE = "2026-10-14T00:00:00+00:00";

// Whether the album itself is free for this order (album_offered in the
// backend): test week, an order placed at 0 for the album, or one placed
// before the test week.
export function albumOffered(order) {
  if (FREE_TRIAL || !order?.unit_price_cents) return true;
  return !!order.created_at && String(order.created_at) < OFFERED_BEFORE;
}

// Between two tiers, the tier above is charged.
export const PAGE_TIERS = [24, 50, 100, 150];

// The most pages an album can have: the largest tier plus a margin for a
// few pages added by hand in the editor. Same as MAX_ALBUM_PAGES in
// backend/app/schemas.py, which refuses more.
export const MAX_ALBUM_PAGES = 160;

export const PRICE_TABLE = {
  A5: { 24: 43, 50: 63, 100: 83, 150: 113 },
  A4: { 24: 53, 50: 73, 100: 99, 150: 129 },
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

// A digital album (the PDF to download): one fixed price whatever its
// format and page count — keep in sync with DIGITAL_PRICE_CENTS in
// backend/app/services/pricing.py, which charges it.
export const DIGITAL_PRICE = 25;

// size/pageCount kept for the callers: the price is the same for all.
export function computeDigitalPrice(size, pageCount, freeTrial = false) {
  return freeTrial ? 0 : DIGITAL_PRICE;
}

// Delivery (Lebanon only), per order — keep in sync with SHIPPING_PRICE_CENTS
// in backend/app/services/pricing.py, which charges it.
export const SHIPPING_PRICE = 5;

// Version of the terms of sale shown on the site (their "last updated"
// date). Sent with an order when the customer ticks "I accept"; must match
// TERMS_VERSION in backend/app/services/pricing.py.
export const TERMS_VERSION = "2026-10-16";

// What the customer pays for an order, in cents: its total — but only the
// delivery when the album is offered (same as cash_due in
// backend/app/services/wakilni.py), and nothing for a PDF while online
// payment isn't set up (it's handed over at once).
export function amountDueCents(order) {
  if (order?.kind === "digital") return 0;
  if (!albumOffered(order)) return order?.total_price_cents || 0;
  return order?.shipping_price_cents ?? SHIPPING_PRICE * 100;
}
