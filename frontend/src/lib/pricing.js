// Kept in sync with the backend's ORDER_PRICE_CENTS / compute_order_price_cents
// — shown here for live price previews (while choosing a page count during
// album creation, and again in the order summary); the backend always
// recomputes and owns the real charged price.
//
// Single shared source for both CreateAlbum.jsx (StepFormat, so the person
// can see what they'll pay while they're still choosing) and
// OrderCheckoutPage.jsx — previously each page kept its own copy of this
// table, which is exactly the kind of duplication that quietly drifts out
// of sync (see recommendedMinPhotos, which did).

export const PAGE_TIERS = [24, 50, 100, 150, 250];

export const PRICE_TABLE = {
  A5: { 24: 25, 50: 35, 100: 55, 150: 75, 250: 110 },
  A4: { 24: 35, 50: 49, 100: 79, 150: 109, 250: 159 },
  A3: { 24: 55, 50: 75, 100: 119, 150: 169, 250: 249 },
};

export const OVERAGE_PER_PAGE = { A5: 0.3, A4: 0.45, A3: 0.7 };

export function computeUnitPrice(size, targetPages) {
  const tierPrices = PRICE_TABLE[size] || PRICE_TABLE.A4;
  if (tierPrices[targetPages] != null) return tierPrices[targetPages];
  const lowerTiers = PAGE_TIERS.filter((t) => t <= targetPages);
  const baseTier = lowerTiers.length ? Math.max(...lowerTiers) : Math.min(...PAGE_TIERS);
  const extraPages = Math.max(0, targetPages - baseTier);
  return tierPrices[baseTier] + extraPages * (OVERAGE_PER_PAGE[size] || OVERAGE_PER_PAGE.A4);
}
