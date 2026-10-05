import { describe, expect, it } from "vitest";
import { spacingSnap } from "./spacingGuides";

const box = (x, y, w, h) => ({ x, y, w, h });

describe("spacingSnap", () => {
  it("centres an item between the page edges and marks both margins", () => {
    const r = spacingSnap(0.255, 0.5, 0.1, 0.2, [], "x");
    expect(r.value).toBeCloseTo(0.25);
    expect(r.marks).toEqual([
      { axis: "x", from: 0, to: 0.25, at: 0.2 },
      { axis: "x", from: 0.75, to: 1, at: 0.2 },
    ]);
  });

  it("mirrors another item: my left margin = its right margin", () => {
    const other = box(0.6, 0.5, 0.3, 0.2); // right margin 0.1
    const r = spacingSnap(0.105, 0.2, 0.1, 0.2, [other], "x");
    expect(r.value).toBeCloseTo(0.1);
    expect(r.marks[0].from).toBe(0);
    expect(r.marks[0].to).toBeCloseTo(0.1);
    expect(r.marks[1].from).toBeCloseTo(0.9);
    expect(r.marks[1].to).toBe(1);
  });

  it("repeats a space already on the page between two photos", () => {
    // a and b side by side with a 0.05 space; c is placed after b.
    const a = box(0.05, 0.1, 0.2, 0.3);
    const b = box(0.3, 0.1, 0.2, 0.3);
    const r = spacingSnap(0.557, 0.2, 0.1, 0.3, [a, b], "x");
    expect(r.value).toBeCloseTo(0.55);
    expect(r.marks.some((m) => Math.abs(m.from - 0.5) < 1e-9 && Math.abs(m.to - 0.55) < 1e-9)).toBe(true);
    expect(r.marks.some((m) => Math.abs(m.from - 0.25) < 1e-9 && Math.abs(m.to - 0.3) < 1e-9)).toBe(true);
  });

  it("puts an item right in the middle of its two neighbours", () => {
    const left = box(0.05, 0.4, 0.2, 0.2);
    const right = box(0.75, 0.4, 0.2, 0.2);
    // Same space on both sides: x = (0.25 + 0.75 - 0.3) / 2 = 0.35, which is also
    // centred on the page here; either way the result is 0.35.
    const r = spacingSnap(0.356, 0.3, 0.4, 0.2, [left, right], "x");
    expect(r.value).toBeCloseTo(0.35);
  });

  it("works vertically too", () => {
    const r = spacingSnap(0.402, 0.2, 0.1, 0.3, [], "y");
    expect(r.value).toBeCloseTo(0.4);
    expect(r.marks.every((m) => m.axis === "y")).toBe(true);
  });

  it("does nothing far from every equal spacing", () => {
    expect(spacingSnap(0.03, 0.2, 0.1, 0.2, [box(0.5, 0.5, 0.2, 0.2)], "x")).toBe(null);
  });

  it("never snaps an item off the page", () => {
    const other = box(0.0, 0.5, 0.05, 0.2); // left margin 0: "my right margin = 0" would need x = 1 - w
    const r = spacingSnap(0.79, 0.2, 0.1, 0.2, [other], "x");
    expect(r === null || r.value + 0.2 <= 1 + 1e-9).toBe(true);
  });
});
