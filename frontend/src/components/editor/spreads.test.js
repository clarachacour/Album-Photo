import { describe, expect, it } from "vitest";
import { spreadNumberToPageCount, viewForPage } from "@/components/editor/spreads";
import { movePage } from "@/components/editor/PageOverview";

describe("the page overview", () => {
  it("opens a page on the spread that shows it", () => {
    // Views: 0 cover, 1 [blank + page 0], 2 [pages 1-2], 3 [pages 3-4]…
    expect([0, 1, 2, 3, 4, 5].map(viewForPage)).toEqual([1, 2, 2, 3, 3, 4]);
    // Consistent with the spread numbers shown ("Double-page N" = view + 1,
    // which ends after spreadNumberToPageCount(N) pages): each page is on
    // the spread opened for it.
    for (let i = 0; i < 9; i += 1) {
      const lastShown = spreadNumberToPageCount(viewForPage(i) + 1) - 1;
      expect(i <= lastShown && i >= lastShown - 1).toBe(true);
    }
  });

  it("moves a page to where it's dropped, the others keeping their order", () => {
    const pages = ["a", "b", "c", "d"];
    expect(movePage(pages, 0, 2)).toEqual(["b", "c", "a", "d"]);
    expect(movePage(pages, 3, 0)).toEqual(["d", "a", "b", "c"]);
    expect(movePage(pages, 1, 1)).toBe(pages);
    expect(movePage(pages, 1, 9)).toBe(pages);
  });
});
