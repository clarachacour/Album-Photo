import { describe, it, expect } from "vitest";
import { rotationFromDrag } from "./DraggableItem";
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
