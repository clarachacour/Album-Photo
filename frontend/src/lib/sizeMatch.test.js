import { describe, expect, it } from "vitest";
import { facingPageIndex, snapToSameSize, spreadPhotoFrames } from "./sizeMatch";

describe("facingPageIndex", () => {
  it("pairs pages as the flipbook shows them", () => {
    expect(facingPageIndex(0, 10)).toBe(null); // facing the blank inside cover
    expect(facingPageIndex(1, 10)).toBe(2);
    expect(facingPageIndex(2, 10)).toBe(1);
    expect(facingPageIndex(9, 10)).toBe(null); // facing the blank before the back cover
  });
});

describe("spreadPhotoFrames", () => {
  it("takes the photo frames of the page and of the facing page, not the one being resized", () => {
    const pages = [
      { items: [{ id: "a", type: "photo", w: 0.4, h: 0.3 }] },
      { items: [{ id: "b", type: "photo", w: 0.5, h: 0.4 }, { id: "t", type: "text", w: 0.5, h: 0.1 }] },
      { items: [{ id: "c", type: "photo", w: 0.45, h: 0.35 }, { id: "d", type: "photo", w: 0.2, h: 0.2 }] },
    ];
    expect(spreadPhotoFrames(pages, 2, "d").map((f) => f.id)).toEqual(["c", "b"]);
  });
});

describe("snapToSameSize", () => {
  const frames = [
    { id: "same-page", w: 0.4, h: 0.3, pageIndex: 1 },
    { id: "facing", w: 0.5, h: 0.45, pageIndex: 2 },
  ];

  it("snaps to the exact size of a frame that's close", () => {
    const r = snapToSameSize(0.408, 0.293, frames);
    expect(r).toMatchObject({ w: 0.4, h: 0.3, snappedW: true, snappedH: true });
    expect(r.matches).toEqual([{ id: "same-page", pageIndex: 1, kind: "both" }]);
  });

  it("matches a frame on the facing page too", () => {
    const r = snapToSameSize(0.495, 0.2, frames);
    expect(r.w).toBe(0.5);
    expect(r.matches).toEqual([{ id: "facing", pageIndex: 2, kind: "w" }]);
  });

  it("can match one frame's width and another's height", () => {
    const r = snapToSameSize(0.402, 0.448, frames);
    expect(r.matches).toEqual([
      { id: "same-page", pageIndex: 1, kind: "w" },
      { id: "facing", pageIndex: 2, kind: "h" },
    ]);
  });

  it("never snaps to a size that would go past the page edge", () => {
    const r = snapToSameSize(0.495, 0.2, frames, { maxW: 0.497 });
    expect(r.snappedW).toBe(false);
    expect(r.w).toBe(0.495);
  });

  it("leaves a size far from every other as it is", () => {
    expect(snapToSameSize(0.7, 0.6, frames)).toEqual({ w: 0.7, h: 0.6, snappedW: false, snappedH: false, matches: [] });
  });
});
