import { describe, it, expect } from "vitest";
import { clampDegrees } from "./CoverEditorPanel";

describe("clampDegrees", () => {
  it("reads typed angles, within -180..180", () => {
    expect(clampDegrees("45")).toBe(45);
    expect(clampDegrees("-12,6")).toBe(-13);
    expect(clampDegrees("400")).toBe(180);
    expect(clampDegrees("abc")).toBeNull();
  });
});
