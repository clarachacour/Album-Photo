import { describe, expect, it } from "vitest";
import { PRICE_TABLE, amountDueCents, billedPageCount, billedTier, computeDigitalPrice, computeUnitPrice, tierMaxPages } from "@/lib/pricing";

describe("pricing", () => {
  it("bills an album as the nearest tier, as the printer does", () => {
    expect(billedTier(15)).toBe(24); // 24 pages is the minimum
    expect(billedTier(24)).toBe(24);
    expect(billedTier(28)).toBe(24);
    expect(billedTier(40)).toBe(50);
    expect(billedTier(37)).toBe(50); // halfway: the tier above
    expect(billedTier(120)).toBe(100);
    expect(billedTier(160)).toBe(150);
    expect(computeUnitPrice("A4", 15, false)).toBe(PRICE_TABLE.A4[24]);
    expect(computeUnitPrice("A5", 28, false)).toBe(PRICE_TABLE.A5[24]);
    expect(computeUnitPrice("A4", 160, false)).toBe(PRICE_TABLE.A4[150]);
  });

  it("tells up to how many pages an album keeps its price", () => {
    expect(tierMaxPages(24)).toBe(36);
    expect(tierMaxPages(50)).toBe(74);
    expect(tierMaxPages(100)).toBe(124);
    expect(tierMaxPages(150)).toBe(160);
    for (const tier of [24, 50, 100]) expect(billedTier(tierMaxPages(tier) + 1)).not.toBe(tier);
  });

  it("uses the price list: 24/50/100/150 pages", () => {
    expect(PRICE_TABLE.A4).toEqual({ 24: 53, 50: 73, 100: 99, 150: 129 });
    expect(PRICE_TABLE.A5).toEqual({ 24: 43, 50: 63, 100: 83, 150: 113 });
  });

  it("counts the album's real pages, not the ones chosen", () => {
    expect(billedPageCount({ target_pages: 50, pages: new Array(15).fill({}) })).toBe(15);
    expect(billedPageCount({ target_pages: 50, pages: [] })).toBe(50);
  });

  it("prices the digital album $22, whatever its size and pages", () => {
    expect(computeDigitalPrice("A5", 24, false)).toBe(22);
    expect(computeDigitalPrice("A4", 150, false)).toBe(22);
  });

  it("makes every album free during the test week (delivery stays)", () => {
    expect(computeUnitPrice("A4", 200, true)).toBe(0);
    expect(computeDigitalPrice("A5", 24, true)).toBe(0);
  });

  it("asks for the total in cash, but only the delivery for an offered album", () => {
    const order = { kind: "print", unit_price_cents: 3500, total_price_cents: 4000, shipping_price_cents: 500, created_at: "2026-10-20T09:00:00+00:00" };
    expect(amountDueCents(order)).toBe(4000);
    // Placed before the test week, or at 0 for the album during it: offered.
    expect(amountDueCents({ ...order, created_at: "2026-10-10T09:00:00+00:00" })).toBe(500);
    expect(amountDueCents({ ...order, unit_price_cents: 0, total_price_cents: 500 })).toBe(500);
    // A PDF: nothing to pay while online payment isn't set up.
    expect(amountDueCents({ kind: "digital", unit_price_cents: 2500, total_price_cents: 2500 })).toBe(0);
  });
});
