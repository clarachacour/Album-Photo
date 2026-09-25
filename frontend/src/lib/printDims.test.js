import { describe, expect, it } from "vitest";
import { coverSpreadLayout, printerCoverTemplate, spineRatio } from "@/lib/printDims";

describe("printer cover template", () => {
  it("A4 portrait up to 50 pages uses the printer's template", () => {
    expect(printerCoverTemplate("A4", "portrait", 1)).not.toBeNull();
    expect(printerCoverTemplate("a4", "portrait", 50)).not.toBeNull();
  });

  it("other formats and page counts have no template yet", () => {
    expect(printerCoverTemplate("A4", "portrait", 51)).toBeNull();
    expect(printerCoverTemplate("A4", "landscape", 24)).toBeNull();
    expect(printerCoverTemplate("A5", "portrait", 24)).toBeNull();
    expect(printerCoverTemplate("A4", "portrait", 0)).toBeNull();
  });

  it("matches Template_A4_1-50pgs.pdf", () => {
    const l = coverSpreadLayout(printerCoverTemplate("A4", "portrait", 40));
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

  it("the cover faces keep the A4 proportions", () => {
    const l = coverSpreadLayout(printerCoverTemplate("A4", "portrait", 40));
    expect(l.front.w / l.front.h).toBeCloseTo(210 / 297, 2);
  });

  it("the editor shows the template's spine", () => {
    expect(spineRatio("A4", "portrait", 40)).toBeCloseTo(7 / 205);
  });
});
