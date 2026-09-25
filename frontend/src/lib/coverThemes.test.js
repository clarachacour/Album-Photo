import { describe, expect, it } from "vitest";
import { COVER_THEMES, spineLogoSource } from "@/lib/coverThemes";

const templates = COVER_THEMES.flatMap((t) => t.templates);
const logoOf = (id) => templates.find((t) => t.id === id).cover.spine_logo_image;

describe("spine logo", () => {
  it("the upscaled logos are the ones templates use", () => {
    for (const id of ["family-mom", "family-dad"]) expect(logoOf(id).startsWith("data:image/webp")).toBe(true);
  });

  it("albums holding an old small logo get the upscaled one", () => {
    // Start of the old PNGs (their header holds the image size).
    const old = {
      "family-mom": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADoAAAA4CAYAAACsc+sjAAAf+UlEQVR42j276Y4cWZqe+ZzVNt9iZwS3JJNLbrV0t9SNqdbM/BAwA93CYPRHlyDdQOuSNAIESQ2NegR0t4RqVWdVZW",
      "family-dad": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEwAAABLCAYAAADakmGTAAA3jklEQVR42lW8Z49lV5qd+Wxz/PXh00dGpCOTSSZdsYqsYjk5SEJL6mkBg/kz8zNmMB8GM0KrBfSHlhqYaT+qUjWLpu",
    };
    for (const [id, png] of Object.entries(old)) expect(spineLogoSource(png + "AAAA")).toBe(logoOf(id));
    expect(spineLogoSource("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAGcAAABMCAYAAABwKqkMAABYGUlEQVR42k39e5RdZ3kmiD/ffe999rnU/aqqkqpkCSQQicDqxg0O+BerGye4g7uhY4idkLQhToasITPMNL1C95CErM")).toMatch(/^data:image\/webp/);
    expect(spineLogoSource("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEkAAAA6CAYAAAD8xXSzAAAg5UlEQVR42m2caZMjuXaenwMgFyb3YlX1NiNbEQ7JEf7/f0SydMMOy9Lc6e7ppTZuuQI4/gCQVXPlmWBMs7lkEjjbu2")).toMatch(/^data:image\/webp/);
  });

  it("albums holding the redrawn vector heart get the original heart back", () => {
    const svg = "data:image/svg+xml;utf8," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path transform="rotate(84 50 50)" d="M50 86Z"/></svg>');
    expect(spineLogoSource(svg)).toBe(logoOf("family-mom"));
  });

  it("leaves any other logo alone", () => {
    expect(spineLogoSource("data:image/png;base64,AAAA")).toBe("data:image/png;base64,AAAA");
    expect(spineLogoSource(undefined)).toBeUndefined();
  });

  it("no template shows the spine year any more", () => {
    for (const tpl of templates) expect(tpl.cover).not.toHaveProperty("spine_year_hidden");
  });
});
