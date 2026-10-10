import { describe, expect, it } from "vitest";
import { darkPhotoItems, isLowResolution, isTooDark, lowResolutionItems, photoPrintDpi } from "@/lib/printQuality";

// A full A4 portrait page: 210 × 297 mm, 8.27 in wide.
const fullPage = { x: 0, y: 0, w: 1, h: 1, scale: 1 };

describe("photoPrintDpi", () => {
  it("a 12 MP photo filling an A4 page prints above 300 dpi", () => {
    // 3024 × 4032 (3:4) is a bit wider than the page (1:1.414): its height
    // covers the page's 297 mm, the sides are cropped.
    const dpi = photoPrintDpi(fullPage, { width: 3024, height: 4032 }, "A4", "portrait");
    expect(dpi).toBeCloseTo(4032 / (297 / 25.4), 0);
    expect(dpi).toBeGreaterThan(300);
  });

  it("zooming in lowers the resolution", () => {
    const photo = { width: 3024, height: 4032 };
    const zoomed = photoPrintDpi({ ...fullPage, scale: 2 }, photo, "A4", "portrait");
    expect(zoomed).toBeCloseTo(photoPrintDpi(fullPage, photo, "A4", "portrait") / 2, 0);
  });

  it("is unknown without the photo's size", () => {
    expect(photoPrintDpi(fullPage, {}, "A4", "portrait")).toBeNull();
    expect(isLowResolution(fullPage, undefined, "A4", "portrait")).toBe(false);
  });

  it("a small photo on a full page is flagged, the same photo in a small frame is not", () => {
    const small = { width: 800, height: 1100 };
    expect(isLowResolution(fullPage, small, "A4", "portrait")).toBe(true); // ~97 dpi
    expect(isLowResolution({ x: 0, y: 0, w: 0.3, h: 0.3, scale: 1 }, small, "A4", "portrait")).toBe(false);
  });
});

describe("lowResolutionItems", () => {
  it("lists the frames at risk, with their page", () => {
    const album = {
      size: "A4",
      orientation: "portrait",
      photos: [{ id: "big", width: 4000, height: 5000 }, { id: "small", width: 600, height: 800 }],
      pages: [
        { items: [{ type: "photo", photo_id: "big", ...fullPage }, { type: "text" }] },
        { items: [{ type: "photo", photo_id: "small", ...fullPage }, { type: "photo", photo_id: null, ...fullPage }] },
      ],
    };
    expect(lowResolutionItems(album).map((f) => [f.pageIndex, f.item.photo_id])).toEqual([[1, "small"]]);
  });
});

describe("isTooDark", () => {
  it("flags an underexposed photo", () => {
    expect(isTooDark({ brightness: 0.16, highlights: 0.3 })).toBe(true);
    expect(isTooDark({ brightness: 0.08, highlights: 0.9 })).toBe(true);
  });

  it("leaves a sunset, a normal photo or an unmeasured one alone", () => {
    expect(isTooDark({ brightness: 0.2, highlights: 0.7 })).toBe(false);
    expect(isTooDark({ brightness: 0.45, highlights: 0.8 })).toBe(false);
    expect(isTooDark({ width: 4000, height: 3000 })).toBe(false);
  });

  it("lists the album's frames holding a dark photo", () => {
    const album = {
      photos: [{ id: "dark", brightness: 0.1, highlights: 0.2 }, { id: "fine", brightness: 0.5, highlights: 0.8 }],
      pages: [{ items: [{ type: "photo", photo_id: "fine" }] }, { items: [{ type: "photo", photo_id: "dark" }, { type: "text" }] }],
    };
    expect(darkPhotoItems(album).map((f) => f.pageIndex)).toEqual([1]);
  });
});
