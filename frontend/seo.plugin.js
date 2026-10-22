// Search engines: writes robots.txt and sitemap.xml at build time, and puts
// the site's full address in the link-preview tags of index.html.
//
// Only the production site may be indexed. Vercel says which one it is
// building (VERCEL_ENV) and the production address
// (VERCEL_PROJECT_PRODUCTION_URL, your custom domain once it's set);
// REACT_APP_SITE_URL overrides the address. Every other build (the dev /
// preview sites, a local build) tells search engines to stay away, so they
// never compete with the real site in search results.

import { PUBLIC_PAGES, localePath } from "./src/lib/localePath.js";

// Public pages listed in the sitemap: each in English and in French.
const LANGUAGES = ["en", "fr"];
// Pages behind a login or for machines: never worth indexing.
const PRIVATE_PATHS = ["/dashboard", "/editor/", "/create", "/choose-template", "/order/", "/orders", "/cart", "/account", "/admin/", "/print/", "/mobile-upload/", "/everbook-statement", "/printer/", "/verify-email", "/reset-password", "/forgot-password"];

export function siteInfo(env = process.env) {
  const raw = env.REACT_APP_SITE_URL || (env.VERCEL_PROJECT_PRODUCTION_URL ? `https://${env.VERCEL_PROJECT_PRODUCTION_URL}` : "");
  const siteUrl = raw.replace(/\/+$/, "");
  const indexable = Boolean(siteUrl) && (env.VERCEL_ENV === "production" || env.SITE_INDEXABLE === "true");
  return { siteUrl, indexable };
}

export function robotsTxt({ siteUrl, indexable }) {
  if (!indexable) return "User-agent: *\nDisallow: /\n";
  return ["User-agent: *", "Allow: /", ...PRIVATE_PATHS.map((p) => `Disallow: ${p}`), "", `Sitemap: ${siteUrl}/sitemap.xml`, ""].join("\n");
}

export function sitemapXml({ siteUrl }) {
  const address = (p, lng) => siteUrl + localePath(p, lng);
  // Each address with its other-language versions (hreflang), as on the pages.
  const urls = PUBLIC_PAGES.flatMap((p) =>
    LANGUAGES.map((lng) => {
      const alternates = LANGUAGES.map((l) => `<xhtml:link rel="alternate" hreflang="${l}" href="${address(p, l)}"/>`).join("");
      return `  <url><loc>${address(p, lng)}</loc>${alternates}</url>`;
    })
  ).join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n${urls}\n</urlset>\n`;
}

export default function seoPlugin() {
  const info = siteInfo();
  return {
    name: "everbook-seo",
    transformIndexHtml(html) {
      // Link previews (WhatsApp, Facebook…) need full addresses.
      const base = info.siteUrl;
      let out = html.replaceAll("%SITE_URL%", base);
      if (!info.indexable) out = out.replace("</head>", '    <meta name="robots" content="noindex, nofollow" />\n    </head>');
      return out;
    },
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "robots.txt", source: robotsTxt(info) });
      if (info.indexable) this.emitFile({ type: "asset", fileName: "sitemap.xml", source: sitemapXml(info) });
    },
  };
}
