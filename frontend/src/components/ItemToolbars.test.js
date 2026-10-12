import { describe, expect, it } from "vitest";
import { toolbarShift } from "@/components/ItemToolbars";

// The toolbar's on-screen box once shifted by `shift` CSS px, on a page
// drawn `scale` times larger: what the browser would measure.
function measure(baseLeft, cssWidth, shift, scale) {
  const left = baseLeft + shift * scale;
  return { left, right: left + cssWidth * scale, width: cssWidth * scale };
}

describe("toolbarShift", () => {
  it.each([1, 0.5, 3])("brings a toolbar off the left edge back on screen at once (scale %s)", (scale) => {
    const shift = toolbarShift(measure(-60, 200, 0, scale), 200, 0, 400);
    const after = measure(-60, 200, shift, scale);
    expect(after.left).toBeCloseTo(4);
    // Measured again where it now is: no further move (it used to keep
    // moving on a scaled page: "Maximum update depth exceeded").
    expect(toolbarShift(after, 200, shift, 400)).toBeCloseTo(shift);
  });

  it("slides one off the right edge back left, and leaves one on screen alone", () => {
    const shift = toolbarShift(measure(300, 200, 0, 3), 200, 0, 800);
    expect(measure(300, 200, shift, 3).right).toBeCloseTo(796);
    expect(toolbarShift(measure(100, 100, 0, 2), 100, 0, 800)).toBe(0);
  });
});
