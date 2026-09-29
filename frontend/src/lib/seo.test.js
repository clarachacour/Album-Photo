import { describe, expect, it } from "vitest";
import { robotsTxt, siteInfo, sitemapXml } from "../../seo.plugin.js";

describe("search engines", () => {
  it("only the production site is indexable", () => {
    expect(siteInfo({ VERCEL_ENV: "production", VERCEL_PROJECT_PRODUCTION_URL: "everbook.fr" })).toEqual({ siteUrl: "https://everbook.fr", indexable: true });
    expect(siteInfo({ VERCEL_ENV: "preview", VERCEL_PROJECT_PRODUCTION_URL: "everbook.fr" }).indexable).toBe(false);
    expect(siteInfo({}).indexable).toBe(false);
  });

  it("a non-production site asks search engines to stay away", () => {
    expect(robotsTxt({ indexable: false })).toBe("User-agent: *\nDisallow: /\n");
  });

  it("production allows public pages and points to the sitemap", () => {
    const robots = robotsTxt({ siteUrl: "https://everbook.fr", indexable: true });
    expect(robots).toContain("Allow: /");
    expect(robots).toContain("Disallow: /editor/");
    expect(robots).toContain("Sitemap: https://everbook.fr/sitemap.xml");
    const sitemap = sitemapXml({ siteUrl: "https://everbook.fr" });
    expect(sitemap).toContain("<loc>https://everbook.fr/</loc>");
    expect(sitemap).toContain("<loc>https://everbook.fr/faq</loc>");
    expect(sitemap).not.toContain("/dashboard");
  });
});
