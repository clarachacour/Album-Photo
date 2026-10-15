import { describe, it, expect } from "vitest";
import { cropPatch, coverSize, pageAspect } from "@/lib/photoFit";
import { edgeResize } from "@/components/book/DraggableItem";

// Where the photo sits on the page (page height = 1), frame not turned.
function photoOnPage(item, orientation, photoAspect) {
  const pa = pageAspect(orientation);
  const fw = item.w * pa, fh = item.h;
  const c = coverSize(fw / fh, photoAspect);
  const z = item.scale ?? 1;
  const iw = c.w * z * fw, ih = c.h * z * fh;
  return { left: item.x * pa + (fw - iw) * (item.focal_x ?? 0.5), top: item.y + (fh - ih) * (item.focal_y ?? 0.5), w: iw, h: ih };
}

const ds = (extra) => ({ startX: 0, startY: 0, startItemX: 0.2, startItemY: 0.2, startItemW: 0.4, startItemH: 0.3, rectW: 1000, rectH: 1000, rotation: 0, ...extra });

describe("edgeResize", () => {
  it("left side: the right side stays put", () => {
    const r = edgeResize(ds({ hx: -1, hy: 0 }), -100, 37, 0.05, 0.03);
    expect(r.x).toBeCloseTo(0.1);
    expect(r.w).toBeCloseTo(0.5);
    expect(r.y).toBeCloseTo(0.2);
    expect(r.h).toBeCloseTo(0.3);
  });

  it("top-left corner moves both", () => {
    const r = edgeResize(ds({ hx: -1, hy: -1 }), 50, 50, 0.05, 0.03);
    expect(r.x).toBeCloseTo(0.25);
    expect(r.y).toBeCloseTo(0.25);
    expect(r.x + r.w).toBeCloseTo(0.6);
    expect(r.y + r.h).toBeCloseTo(0.5);
  });

  it("stays on the page", () => {
    const r = edgeResize(ds({ hx: -1, hy: 0 }), -900, 0, 0.05, 0.03);
    expect(r.x).toBeCloseTo(0);
    expect(r.w).toBeCloseTo(0.6);
  });

  it("a turned frame keeps its far side in place", () => {
    const d = ds({ hx: 1, hy: 0, rotation: 90 });
    // Turned a quarter: its width runs downwards on screen.
    const r = edgeResize(d, 0, 100, 0.05, 0.03);
    expect(r.w).toBeCloseTo(0.5);
    // Center moved down by half the growth.
    expect(r.y + r.h / 2).toBeCloseTo(0.35 + 0.05);
    expect(r.x + r.w / 2).toBeCloseTo(0.4);
  });
});

describe("cropPatch", () => {
  const item = { x: 0.2, y: 0.2, w: 0.4, h: 0.3, scale: 1, focal_x: 0.5, focal_y: 0.5 };
  const aspect = 1.5;

  it("cropping a side leaves the photo where it was", () => {
    const before = photoOnPage(item, "portrait", aspect);
    const patch = cropPatch(item, { x: 0.3, y: 0.2, w: 0.3, h: 0.3 }, "portrait", aspect);
    const after = photoOnPage({ ...item, ...patch }, "portrait", aspect);
    expect(after.left).toBeCloseTo(before.left, 6);
    expect(after.top).toBeCloseTo(before.top, 6);
    expect(after.w).toBeCloseTo(before.w, 6);
    expect(after.h).toBeCloseTo(before.h, 6);
  });

  it("the bottom-right corner too (only w/h)", () => {
    const before = photoOnPage(item, "landscape", aspect);
    const patch = cropPatch(item, { w: 0.25, h: 0.2 }, "landscape", aspect);
    const after = photoOnPage({ ...item, ...patch }, "landscape", aspect);
    expect(after.left).toBeCloseTo(before.left, 6);
    expect(after.top).toBeCloseTo(before.top, 6);
    expect(after.w).toBeCloseTo(before.w, 6);
  });

  it("pulled past the photo's edge, the photo grows to fill the frame", () => {
    const patch = cropPatch(item, { y: 0.2, h: 0.8 }, "portrait", aspect);
    expect(patch.scale).toBeGreaterThanOrEqual(1);
    const after = photoOnPage({ ...item, ...patch }, "portrait", aspect);
    expect(after.h).toBeGreaterThanOrEqual(0.8 - 1e-9);
  });

  it("a photo turned in its frame and plain moves are left alone", () => {
    expect(cropPatch({ ...item, rotation: 10 }, { w: 0.3 }, "portrait", aspect)).toEqual({ w: 0.3 });
    expect(cropPatch(item, { x: 0.1, y: 0.1 }, "portrait", aspect)).toEqual({ x: 0.1, y: 0.1 });
  });
});
