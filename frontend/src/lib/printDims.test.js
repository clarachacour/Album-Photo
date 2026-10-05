import { describe, expect, it } from "vitest";
import { coverSpreadLayout, pageDimsMm, printerCoverTemplate, spineRatio, spineWidthMm, TEMPLATE_A4_1_50 } from "@/lib/printDims";

describe("printer cover template", () => {
  it("no album uses a printer template: every cover has the original layout", () => {
    expect(printerCoverTemplate("A4", "portrait", 1)).toBeNull();
    expect(printerCoverTemplate("A4", "portrait", 24)).toBeNull();
    expect(printerCoverTemplate("A4", "portrait", 50)).toBeNull();
    expect(printerCoverTemplate("A4", "landscape", 24)).toBeNull();
    expect(printerCoverTemplate("A5", "portrait", 24)).toBeNull();
  });

  it("the editor shows the original spine width", () => {
    expect(spineRatio("A4", "portrait", 40)).toBeCloseTo(spineWidthMm(40) / pageDimsMm("A4", "portrait").w);
  });

  // The template is kept (unused) to be switched back on if needed.
  it("the kept template still matches Template_A4_1-50pgs.pdf", () => {
    const l = coverSpreadLayout(TEMPLATE_A4_1_50);
    expect(l.trim).toEqual({ x: 5, y: 5, w: 475, h: 330 });
    expect(l.sheet).toEqual({ w: 485, h: 340 });
    // Guide lines of the template, from the trimmed edge: 20 / 225 / 234 / 241 / 250 / 455 mm.
    const fromTrim = (x) => x - l.trim.x;
    expect(fromTrim(l.back.x)).toBe(20);
    expect(fromTrim(l.back.x + l.back.w)).toBe(225);
    expect(fromTrim(l.spine.x)).toBe(234);
    expect(fromTrim(l.spine.x + l.spine.w)).toBe(241);
    expect(fromTrim(l.front.x)).toBe(250);
    expect(fromTrim(l.front.x + l.front.w)).toBe(455);
    expect(l.front.y - l.trim.y).toBe(20);
    expect(l.front.h).toBe(290);
  });
});
