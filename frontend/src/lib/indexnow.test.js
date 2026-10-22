import { afterEach, describe, expect, it, vi } from "vitest";
import { notifyIndexNow } from "../../scripts/indexnow.mjs";

const SITE = "https://everbook-album.com";

describe("IndexNow, after a production build", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends only the pages that changed, with the site's key", async () => {
    const live = {
      [`${SITE}/`]: '<p>Same</p><script src="/assets/index-OLD.js"></script>',
      [`${SITE}/faq`]: "<p>Old answer</p>",
    };
    const sent = [];
    vi.stubGlobal("fetch", async (url, init) => {
      if (url.includes("indexnow")) {
        sent.push(JSON.parse(init.body));
        return { ok: true, status: 200 };
      }
      return live[url] ? { ok: true, text: async () => live[url] } : { ok: false };
    });
    vi.spyOn(console, "log").mockImplementation(() => {});
    await notifyIndexNow({
      siteUrl: SITE,
      key: "abc",
      pages: [
        { url: `${SITE}/`, html: '<p>Same</p><script src="/assets/index-NEW.js"></script>' }, // only the build changed
        { url: `${SITE}/faq`, html: "<p>New answer</p>" },
        { url: `${SITE}/fr/faq`, html: "<p>Nouvelle</p>" }, // not online yet
      ],
    });
    expect(sent).toEqual([{ host: "everbook-album.com", key: "abc", keyLocation: `${SITE}/abc.txt`, urlList: [`${SITE}/faq`, `${SITE}/fr/faq`] }]);
  });

  it("never stops the build", async () => {
    vi.stubGlobal("fetch", async () => {
      throw new Error("offline");
    });
    vi.spyOn(console, "warn").mockImplementation(() => {});
    await expect(notifyIndexNow({ siteUrl: SITE, key: "abc", pages: [{ url: `${SITE}/`, html: "x" }] })).resolves.toBeUndefined();
  });
});
