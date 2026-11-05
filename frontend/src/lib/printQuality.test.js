import { describe, expect, it } from "vitest";
import { coverPhotoIssues, coverPhotoWarnings, darkPhotoItems, emptyFrames, isLowResolution, isTooDark, lowResolutionItems, photoPrintDpi } from "@/lib/printQuality";

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
  it("flags a dark photo, even with a few bright lights in it", () => {
    // Evening restaurant photos that did print too dark.
    expect(isTooDark({ brightness: 0.215, highlights: 0.49 })).toBe(true);
    expect(isTooDark({ brightness: 0.167, highlights: 0.49 })).toBe(true);
  });

  it("leaves a sunset, a normal photo or an unmeasured one alone", () => {
    expect(isTooDark({ brightness: 0.31, highlights: 0.6 })).toBe(false);
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

describe("the cover and empty frames", () => {
  const album = (cover, pages = []) => ({ size: "A4", orientation: "portrait", pages, cover });
  // A photo filling most of an A4 cover (about 18 × 25 cm).
  const coverPhoto = (extra) => ({ id: "c1", type: "image", is_photo: true, image_url: "x", x: 0.07, y: 0.07, w: 0.86, h: 0.86, ...extra });

  it("flags a cover photo too small for its frame, or dark", () => {
    expect(coverPhotoWarnings(coverPhoto({ photo_width: 640, photo_height: 900 }), "A4", "portrait")).toEqual(["lowResolution"]);
    expect(coverPhotoWarnings(coverPhoto({ photo_width: 3000, photo_height: 4000, brightness: 0.1 }), "A4", "portrait")).toEqual(["tooDark"]);
    expect(coverPhotoWarnings(coverPhoto({ photo_width: 3000, photo_height: 4000, brightness: 0.5 }), "A4", "portrait")).toEqual([]);
  });

  it("measures an older cover photo from its file, and leaves logos alone", () => {
    expect(coverPhotoWarnings(coverPhoto(), "A4", "portrait", { width: 500, height: 700 })).toEqual(["lowResolution"]);
    expect(coverPhotoWarnings(coverPhoto(), "A4", "portrait")).toEqual([]); // size not known yet
    expect(coverPhotoWarnings({ ...coverPhoto({ photo_width: 100, photo_height: 100 }), is_photo: false, asset: "logo" }, "A4", "portrait")).toEqual([]);
    const issues = coverPhotoIssues(album({ back_extra_items: [coverPhoto({ photo_width: 400, photo_height: 600 })] }));
    expect(issues.map((i) => [i.side, i.warnings])).toEqual([["back", ["lowResolution"]]]);
  });

  it("finds the empty photo frames, inside and on the cover", () => {
    const pages = [{ items: [{ type: "photo", photo_id: "p1" }] }, { items: [{ type: "photo" }, { type: "text", content: "" }] }];
    expect(emptyFrames(album({ extra_items: [{ type: "image" }, coverPhoto()] }, pages))).toEqual([{ pageIndex: 1 }, { side: "front" }]);
  });
});
