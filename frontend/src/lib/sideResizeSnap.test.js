import { describe, expect, it } from "vitest";
import { snapSideResize } from "@/lib/sideResizeSnap";

// Two photos side by side, as on the page in question: the left one is the
// reference, the right one is being resized.
const left = { id: "a", x: 0.06, y: 0.05, w: 0.42, h: 0.6 };
const right = { id: "b", x: 0.52, y: 0.05, w: 0.4, h: 0.55 };
const close = (v) => Number(v.toFixed(6));

describe("resizing a frame from a side or a corner", () => {
  it("lines the pulled bottom edge up with the other photo, with a guide", () => {
    const r = snapSideResize(right, { x: 0.52, y: 0.05, w: 0.4, h: 0.592 }, [left]);
    expect(close(r.patch.h)).toBe(0.6);
    expect(close(r.guideY)).toBe(0.65);
    expect(r.patch.y).toBe(0.05); // the top didn't move
  });

  it("pulling the left side keeps the right side where it is", () => {
    const r = snapSideResize(right, { x: 0.489, y: 0.05, w: 0.431, h: 0.55 }, [left]);
    expect(close(r.patch.x)).toBe(0.48); // the left photo's right edge
    expect(close(r.patch.x + r.patch.w)).toBe(0.92);
    expect(close(r.guideX)).toBe(0.48);
  });

  it("pulling the top lines it up with the other photo's top", () => {
    const r = snapSideResize(right, { x: 0.52, y: 0.062, w: 0.4, h: 0.538 }, [left]);
    expect(close(r.patch.y)).toBe(0.05);
    expect(close(r.patch.y + r.patch.h)).toBe(0.6);
  });

  it("takes another photo's size when close, from any side", () => {
    const frames = [{ ...left, pageIndex: 0 }];
    const r = snapSideResize(right, { x: 0.505, y: 0.05, w: 0.415, h: 0.55 }, [left], frames);
    expect(close(r.patch.w)).toBe(0.42);
    expect(close(r.patch.x + r.patch.w)).toBe(0.92); // right side kept
    expect(r.matches.map((m) => m.id)).toEqual(["a"]);
  });

  it("shows the guide line too when the same size also lines the edges up", () => {
    const frames = [{ ...left, pageIndex: 0 }];
    const r = snapSideResize(right, { x: 0.52, y: 0.05, w: 0.4, h: 0.592 }, [left], frames);
    expect(close(r.patch.h)).toBe(0.6);
    expect(close(r.guideY)).toBe(0.65);
  });

  it("leaves a resize far from everything as it is", () => {
    const patch = { x: 0.52, y: 0.05, w: 0.3, h: 0.27 };
    const r = snapSideResize(right, patch, [left]);
    expect(r.patch).toEqual(patch);
    expect([r.guideX, r.guideY]).toEqual([null, null]);
  });
});
