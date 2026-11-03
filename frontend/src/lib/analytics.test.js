import { describe, expect, it } from "vitest";
import { visitUrl } from "./analytics";

describe("visitUrl", () => {
  it("keeps an ad's utm tags and drops the rest of the query", () => {
    expect(visitUrl("https://everbook-album.com/fr?utm_source=instagram&token=secret#top")).toBe("https://everbook-album.com/fr?utm_source=instagram");
  });

  it("leaves out the print, printer and admin pages", () => {
    expect(visitUrl("https://everbook-album.com/print/abc?auth=x")).toBeNull();
    expect(visitUrl("https://everbook-album.com/printer/abc?token=x")).toBeNull();
    expect(visitUrl("https://everbook-album.com/admin/orders")).toBeNull();
    expect(visitUrl("https://everbook-album.com/printing-guide")).toBe("https://everbook-album.com/printing-guide");
  });
});
