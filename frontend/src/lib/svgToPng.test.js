import { describe, expect, it } from "vitest";
import { isSvgFile, svgAspect } from "@/lib/svgToPng";

// The attributes of an <svg> element, as getAttribute reads them.
const svg = (attrs) => ({ getAttribute: (name) => attrs[name] ?? null });

describe("svgToPng", () => {
  it("recognises an SVG by its type or its name", () => {
    expect(isSvgFile({ type: "image/svg+xml", name: "logo" })).toBe(true);
    expect(isSvgFile({ type: "", name: "Logo.SVG" })).toBe(true);
    expect(isSvgFile({ type: "image/png", name: "logo.png" })).toBe(false);
  });

  it("reads its shape from the viewBox, else its width and height", () => {
    expect(svgAspect(svg({ viewBox: "0 0 400 200" }))).toBe(2);
    expect(svgAspect(svg({ width: "100", height: "300" }))).toBeCloseTo(1 / 3);
    expect(svgAspect(svg({}))).toBe(1);
  });
});
