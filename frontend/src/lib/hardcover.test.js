import { describe, expect, it } from "vitest";
import { TEMPLATE_A4_1_50, coverSpreadLayout, hardcoverCoverTemplate, hardcoverSpineMm, pageSheetLayout, withBleed } from "@/lib/printDims";

const r1 = (v) => Math.round(v * 10) / 10;

describe("the one-sheet hardcover format", () => {
  it("gives back the printer's A4 template (1-50 pages) exactly", () => {
    const t = hardcoverCoverTemplate("A4", "portrait", 40);
    expect([t.panelW, t.panelH, t.spine, t.hinge, t.wrap, t.bleed]).toEqual([
      TEMPLATE_A4_1_50.panelW, TEMPLATE_A4_1_50.panelH, TEMPLATE_A4_1_50.spine, TEMPLATE_A4_1_50.hinge, TEMPLATE_A4_1_50.wrap, TEMPLATE_A4_1_50.bleed,
    ]);
    // Template_A4_1-50pgs.pdf: a 489.8 × 344.8 mm sheet, cut at 475 × 330 mm.
    const layout = coverSpreadLayout(t);
    expect([r1(layout.sheet.w), r1(layout.sheet.h)]).toEqual([489.8, 344.8]);
    expect([layout.trim.w, layout.trim.h]).toEqual([475, 330]);
  });

  it("widens the spine with the pages (170 g paper), 7 mm at least", () => {
    expect([24, 50, 100, 150, 160].map(hardcoverSpineMm)).toEqual([7, 7, 11.5, 15.5, 16.5]);
  });

  it("fits the other formats", () => {
    const a5 = hardcoverCoverTemplate("A5", "portrait", 24);
    expect([a5.panelW, a5.panelH]).toEqual([143, 203]);
    const land = hardcoverCoverTemplate("A4", "landscape", 100);
    expect([land.panelW, land.panelH, land.spine]).toEqual([292, 203, 11.5]);
  });

  it("puts each page in the middle of its sheet, with room for the bleed and the marks", () => {
    const sheet = pageSheetLayout("A5", "portrait");
    expect(sheet.trim).toEqual({ x: 8, y: 8, w: 148, h: 210 });
    expect(sheet.sheet).toEqual({ w: 164, h: 226 });
  });

  it("takes a photo touching an edge past it, and leaves the others", () => {
    const items = [
      { id: "full", type: "photo", photo_id: "p", x: 0, y: 0, w: 1, h: 1 },
      { id: "inside", type: "photo", photo_id: "q", x: 0.1, y: 0.1, w: 0.4, h: 0.3 },
      { id: "text", type: "text", x: 0, y: 0, w: 1, h: 0.1 },
    ];
    const [full, inside, text] = withBleed(items, "A4", "portrait", 3);
    expect(r1(full.x * 210)).toBe(-3);
    expect(r1((full.x + full.w) * 210)).toBe(213);
    expect(r1(full.y * 297)).toBe(-3);
    expect(r1((full.y + full.h) * 297)).toBe(300);
    expect(inside).toBe(items[1]);
    expect(text).toBe(items[2]);
  });
});
