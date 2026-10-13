import { describe, expect, it } from "vitest";
import { FREE_TRIAL, PRICE_TABLE, amountDueCents, billedPageCount, billedTier, computeDigitalPrice, computeUnitPrice } from "@/lib/pricing";

describe("pricing", () => {
  it("bills an album as the smallest tier that holds it", () => {
    expect(billedTier(15)).toBe(24); // 24 pages is the minimum
    expect(billedTier(24)).toBe(24);
    expect(billedTier(35)).toBe(50);
    expect(computeUnitPrice("A4", 15, false)).toBe(PRICE_TABLE.A4[24]);
    expect(computeUnitPrice("A5", 35, false)).toBe(PRICE_TABLE.A5[50]);
  });

  it("adds each page past the largest tier", () => {
    expect(computeUnitPrice("A4", 210, false)).toBeCloseTo(PRICE_TABLE.A4[200] + 10 * 0.45);
  });

  it("counts the album's real pages, not the ones chosen", () => {
    expect(billedPageCount({ target_pages: 50, pages: new Array(15).fill({}) })).toBe(15);
    expect(billedPageCount({ target_pages: 50, pages: [] })).toBe(50);
  });

  it("prices the digital album $15 below the printed one", () => {
    expect(computeDigitalPrice("A5", 24, false)).toBe(PRICE_TABLE.A5[24] - 15);
    expect(computeDigitalPrice("A4", 35, false)).toBe(PRICE_TABLE.A4[50] - 15);
  });

  it("makes every album free during the test week (delivery stays)", () => {
    expect(computeUnitPrice("A4", 200, true)).toBe(0);
    expect(computeDigitalPrice("A5", 24, true)).toBe(0);
  });

  it("asks only for the delivery during the test week, even for an older order", () => {
    const old = { kind: "print", total_price_cents: 4000, shipping_price_cents: 500 };
    expect(amountDueCents(old)).toBe(FREE_TRIAL ? 500 : 4000);
    expect(amountDueCents({ kind: "digital", total_price_cents: 2000 })).toBe(FREE_TRIAL ? 0 : 2000);
  });
});
