import { describe, it, expect } from "vitest";
import { rotationFromDrag, rotatedResize, handleSide } from "./DraggableItem";
import { deletePatch } from "@/lib/coverEditing";

describe("rotationFromDrag", () => {
  it("adds the angle turned by the handle", () => {
    expect(rotationFromDrag(0, -90, -60)).toBe(30);
    expect(rotationFromDrag(10, 0, -25)).toBe(-15);
  });
  it("stays within -180..180", () => {
    expect(rotationFromDrag(170, 0, 30)).toBe(-160);
    expect(rotationFromDrag(-170, 0, -30)).toBe(160);
  });
  it("snaps to straight and quarter turns when close", () => {
    expect(rotationFromDrag(0, 0, 3)).toBe(0);
    expect(rotationFromDrag(0, 0, 88)).toBe(90);
    expect(rotationFromDrag(0, 0, -178)).toBe(180);
  });
});

describe("deletePatch", () => {
  it("hides built-in pieces and empties free texts", () => {
    expect(deletePatch("title")).toEqual({ title_hidden: true });
    expect(deletePatch("spine-logo")).toEqual({ spine_logo_hidden: true });
    expect(deletePatch("spine-caption")).toEqual({ spine_caption: "" });
    expect(deletePatch("cover")).toBeNull();
  });
});

describe("rotatedResize", () => {
  const ds = { startItemX: 0.4, startItemY: 0.4, startItemW: 0.2, startItemH: 0.2, rectW: 100, rectH: 100 };
  it("behaves like a plain resize when not turned... except it keeps the top-left corner", () => {
    const r = rotatedResize({ ...ds, rotation: 0.0001 }, 10, 10, 0.05, 0.03);
    expect(r.w).toBeCloseTo(0.3);
    expect(r.h).toBeCloseTo(0.3);
    expect(r.x).toBeCloseTo(0.4, 3);
    expect(r.y).toBeCloseTo(0.4, 3);
  });
  it("reads the drag along the turned sides (90°: dragging down widens)", () => {
    const r = rotatedResize({ ...ds, rotation: 90 }, 0, 10, 0.05, 0.03);
    expect(r.w).toBeCloseTo(0.3);
    expect(r.h).toBeCloseTo(0.2);
  });
});

describe("handleSide", () => {
  it("puts the rotate handle on the side facing up", () => {
    expect(handleSide(0)).toBe("top");
    expect(handleSide(90)).toBe("left");
    expect(handleSide(-90)).toBe("right");
    expect(handleSide(180)).toBe("bottom");
    expect(handleSide(0, true)).toBe("bottom");
  });
});
