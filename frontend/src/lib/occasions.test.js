import { describe, expect, it } from "vitest";
import { OCCASIONS } from "@/lib/occasions";
import { COVER_THEMES } from "@/lib/coverThemes";

describe("the occasion pages", () => {
  it("show every travel template, with the home page's names", () => {
    const travel = COVER_THEMES.find((theme) => theme.id === "travel").templates;
    expect(OCCASIONS.travel.covers).toEqual(travel.map((tpl) => [tpl.landingImage, tpl.name]));
  });

  it("only show covers that exist among the templates", () => {
    const images = new Set(COVER_THEMES.flatMap((theme) => theme.templates.map((tpl) => tpl.landingImage)));
    for (const { covers } of Object.values(OCCASIONS)) for (const [src] of covers) expect(images.has(src), src).toBe(true);
  });
});
