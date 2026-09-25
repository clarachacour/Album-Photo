import { describe, expect, it } from "vitest";
import { clampZoom, coverSize, fitBoxToAspect, fitItemToPhoto, minZoom, pageAspect, photoRect } from "@/lib/photoFit";

const realAspect = (box, orientation) => (box.w / box.h) * pageAspect(orientation);

describe("fitBoxToAspect", () => {
  const slot = { x: 0.05, y: 0.05, w: 0.9, h: 0.43 };
  for (const orientation of ["portrait", "landscape"]) {
    for (const aspect of [0.5, 0.75, 1, 4 / 3, 16 / 9, 3]) {
      it(`${orientation}, photo ${aspect.toFixed(2)}: same proportions as the photo, inside the slot`, () => {
        const box = fitBoxToAspect(slot, aspect, orientation);
        expect(realAspect(box, orientation)).toBeCloseTo(aspect, 6);
        expect(box.x).toBeGreaterThanOrEqual(slot.x - 1e-9);
        expect(box.y).toBeGreaterThanOrEqual(slot.y - 1e-9);
        expect(box.x + box.w).toBeLessThanOrEqual(slot.x + slot.w + 1e-9);
        expect(box.y + box.h).toBeLessThanOrEqual(slot.y + slot.h + 1e-9);
      });
    }
  }

  it("keeps the slot when the photo size is unknown", () => {
    expect(fitBoxToAspect(slot, null, "portrait")).toEqual(slot);
  });
});

describe("zoom", () => {
  it("at zoom 1 the photo exactly covers the frame", () => {
    expect(coverSize(1, 1.5)).toEqual({ w: 1.5, h: 1 });
    expect(coverSize(1, 0.5)).toEqual({ w: 1, h: 2 });
  });

  it("the minimum zoom shows the whole photo, touching two edges", () => {
    const r = photoRect(1, 1.5, minZoom(1, 1.5));
    expect(r.w).toBeCloseTo(1);
    expect(r.h).toBeCloseTo(1 / 1.5);
    expect(r.top).toBeCloseTo((1 - 1 / 1.5) / 2); // centered
  });

  it("a frame with the photo's proportions can't be zoomed out (nothing is hidden)", () => {
    expect(minZoom(1.5, 1.5)).toBeCloseTo(1);
  });

  it("clamps between whole photo and 2.5x", () => {
    expect(clampZoom(0.1, 1, 2)).toBeCloseTo(0.5);
    expect(clampZoom(9, 1, 2)).toBe(2.5);
    expect(clampZoom(undefined, 1, 2)).toBe(1);
  });

  it("matches CSS object-position at zoom 1: focal point 0 aligns the left edges", () => {
    expect(photoRect(1, 2, 1, 0, 0.5).left).toBeCloseTo(0);
    expect(photoRect(1, 2, 1, 1, 0.5).left).toBeCloseTo(-1);
  });
});

describe("fitItemToPhoto", () => {
  const slot = { x: 0.05, y: 0.05, w: 0.9, h: 0.9 };
  const landscape = { id: "l", width: 4000, height: 3000 };
  const portrait = { id: "p", width: 3000, height: 4000 };

  it("fits the frame to the photo inside its slot", () => {
    const fields = fitItemToPhoto({ ...slot }, landscape, "portrait");
    expect(realAspect(fields, "portrait")).toBeCloseTo(4 / 3, 6);
    expect(fields.slot).toEqual(slot);
    expect(fields.photo_aspect).toBeCloseTo(4 / 3);
  });

  it("repeated swaps don't shrink the frame", () => {
    let item = { ...slot };
    for (let i = 0; i < 10; i++) item = { ...item, ...fitItemToPhoto(item, i % 2 ? landscape : portrait, "portrait") };
    expect(item).toMatchObject(fitItemToPhoto({ ...slot }, landscape, "portrait"));
  });

  it("an empty frame takes its whole slot", () => {
    expect(fitItemToPhoto({ x: 0.2, y: 0.2, w: 0.1, h: 0.1, slot }, null, "portrait")).toMatchObject(slot);
  });
});
