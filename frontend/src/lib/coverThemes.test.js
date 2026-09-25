import { describe, expect, it } from "vitest";
import { COVER_THEMES, spineLogoSource } from "@/lib/coverThemes";

const mom = COVER_THEMES.flatMap((t) => t.templates).find((t) => t.id === "family-mom");

describe("spine logo", () => {
  it("the Mom template's heart is a vector image", () => {
    expect(mom.cover.spine_logo_image.startsWith("data:image/svg+xml")).toBe(true);
  });

  it("albums holding the old blurry heart get the vector one", () => {
    const old = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADoAAAA4CAYAAACsc+sjAAAf+UlEQVR42j276Y4cWZqe+ZzVNt9iZwS3JJNLbrV0t9SNqdbM/BAwA93CYPRHlyDdQOuSNAIESQ2NegR0t4RqVWdVZWZlJZlkkkySwVh9N7Ozzg+LKgQcCDgcDjc753zrest";
    expect(spineLogoSource(old)).toBe(mom.cover.spine_logo_image);
  });

  it("leaves any other logo alone", () => {
    expect(spineLogoSource("data:image/png;base64,AAAA")).toBe("data:image/png;base64,AAAA");
    expect(spineLogoSource(undefined)).toBeUndefined();
  });

  it("no template shows the spine year any more", () => {
    for (const tpl of COVER_THEMES.flatMap((t) => t.templates)) expect(tpl.cover).not.toHaveProperty("spine_year_hidden");
  });
});
