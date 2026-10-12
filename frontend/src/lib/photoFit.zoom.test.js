import { describe, it, expect } from "vitest";
import { zoomToFillTurned } from "./photoFit";

describe("zoomToFillTurned", () => {
  it("needs no zoom when straight or upside down", () => {
    expect(zoomToFillTurned(1.5, 0)).toBeCloseTo(1);
    expect(zoomToFillTurned(1.5, 180)).toBeCloseTo(1);
  });
  it("zooms more the more the photo is turned, and for long frames", () => {
    expect(zoomToFillTurned(1, 45)).toBeCloseTo(Math.SQRT2);
    expect(zoomToFillTurned(2, 10)).toBeGreaterThan(zoomToFillTurned(1, 10));
    expect(zoomToFillTurned(1.5, -10)).toBeCloseTo(zoomToFillTurned(1.5, 10));
  });
});
