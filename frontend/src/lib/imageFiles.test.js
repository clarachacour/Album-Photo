import { describe, expect, it } from "vitest";
import { isImageFile } from "./imageFiles";

describe("isImageFile", () => {
  it("accepts photos by type", () => {
    expect(isImageFile({ type: "image/jpeg", name: "a.jpg" })).toBe(true);
  });
  it("accepts an iPhone HEIC photo that has no type", () => {
    expect(isImageFile({ type: "", name: "IMG_0001.HEIC" })).toBe(true);
  });
  it("refuses other files", () => {
    expect(isImageFile({ type: "video/mp4", name: "clip.mp4" })).toBe(false);
    expect(isImageFile({ type: "", name: "notes.txt" })).toBe(false);
  });
});
