// Runs after the two builds (package.json "build"): writes one HTML file per
// public page, holding its text, title and description.
//
//   build/index.html          the home page
//   build/faq.html, …         the other public pages (served at /faq… on
//                             Vercel thanks to "cleanUrls")
//   build/fr.html, build/fr/faq.html, …  their French versions (/fr, /fr/faq…)
//   build/app.html            the empty page for every other address (the
//                             app draws it in the browser). vercel.json
//                             rewrites to "/app", not "/app.html": with
//                             cleanUrls, "/app.html" answers with a redirect
//                             to "/app", which would replace the address the
//                             visitor asked for (a reload of /dashboard
//                             showed "page not found").
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { siteInfo } from "../seo.plugin.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const buildDir = join(root, "build");
const ssrDir = join(root, "build-ssr");

// What the pages' code expects from a browser, as a first-time visitor has it.
const memoryStorage = () => {
  const data = new Map();
  return {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => data.set(k, String(v)),
    removeItem: (k) => data.delete(k),
    clear: () => data.clear(),
  };
};
globalThis.localStorage = memoryStorage();
globalThis.sessionStorage = memoryStorage();

const { render, structuredData, llms, PUBLIC_PAGES, LANGUAGES, localePath } = await import(pathToFileURL(join(ssrDir, "prerender.js")).href);
const template = readFileSync(join(buildDir, "index.html"), "utf8");
const { siteUrl } = siteInfo();

const escapeAttr = (s) => s.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;");
const escapeText = (s) => s.replaceAll("&", "&amp;").replaceAll("<", "&lt;");

function setMeta(html, attr, name, content) {
  const re = new RegExp(`(<meta ${attr}="${name}" content=")[^"]*(")`);
  if (!re.test(html)) throw new Error(`index.html has no <meta ${attr}="${name}">`);
  // A function, not a "$1…$2" string: a "$" in the text ("From $25") would
  // be read as a group reference and cut the description short.
  return html.replace(re, (_, start, end) => `${start}${escapeAttr(content)}${end}`);
}

// Open Graph's name for each language.
const OG_LOCALE = { en: "en_US", fr: "fr_FR" };

function pageHtml(path, lng, { html, title, description }, extraData = []) {
  let out = template;
  if (!out.includes('<div id="root"></div>')) throw new Error('index.html has no empty <div id="root"></div>');
  out = out.replace('<div id="root"></div>', `<div id="root">${html}</div>`);
  out = out.replace('<html lang="en">', `<html lang="${lng}">`);
  // The page shows without JavaScript now: no "enable JavaScript" notice.
  out = out.replace(/\s*<noscript>[\s\S]*?<\/noscript>/, "");
  // The fonts don't hold the page back: it shows at once with the system's
  // fonts, then switches to the site's (display=swap). Only on these public
  // pages: the app's pages (app.html) keep waiting for them, the print page
  // above all, whose PDF must use the right fonts.
  out = out.replace(/<link href="(https:\/\/fonts\.googleapis\.com\/css2[^"]*)" rel="stylesheet" \/>/, (_, href) =>
    `<link href="${href}" rel="stylesheet" media="print" onload="this.media='all'" />\n        <noscript><link href="${href}" rel="stylesheet" /></noscript>`);
  out = out.replace(/<title>[^<]*<\/title>/, () => `<title>${escapeText(title)}</title>`);
  out = setMeta(out, "name", "description", description);
  out = setMeta(out, "property", "og:title", title);
  out = setMeta(out, "property", "og:description", description);
  if (siteUrl) {
    const address = (p, l) => siteUrl + (localePath(p, l) === "/" ? "/" : localePath(p, l));
    const url = address(path, lng);
    out = setMeta(out, "property", "og:url", url);
    // The page, and the same page in each language (hreflang), so search
    // engines show the French one to French speakers; English by default.
    const links = [
      `<link rel="canonical" href="${url}" />`,
      ...LANGUAGES.map((l) => `<link rel="alternate" hreflang="${l}" href="${address(path, l)}" />`),
      `<link rel="alternate" hreflang="x-default" href="${address(path, "en")}" />`,
      `<meta property="og:locale" content="${OG_LOCALE[lng]}" />`,
    ];
    out = out.replace("</head>", () => `  ${links.join("\n    ")}\n  </head>`);
    // The home page tells search engines who Everbook is (the brand shown
    // for a search on its name, with its logo).
    // Then the page's own: the albums and their prices (home), the
    // questions and answers (FAQ).
    const data = path === "/" ? brandData(siteUrl, description, extraData) : extraData[0];
    if (data) out = out.replace("</head>", () => `  <script type="application/ld+json">${JSON.stringify(data).replaceAll("<", "\\u003c")}</script>\n  </head>`);
  }
  return out;
}

function brandData(siteUrl, description, products = []) {
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": `${siteUrl}/#organization`,
        name: "Everbook",
        // "Everbook Album" (the domain, the Instagram account) tells it apart
        // from other businesses named Everbook.
        alternateName: "Everbook Album",
        url: `${siteUrl}/`,
        logo: `${siteUrl}/favicon.png`,
        email: "orders@everbook-album.com",
        // Its accounts: the same business as this site.
        sameAs: ["https://www.instagram.com/everbook_album/"],
        description,
        areaServed: { "@type": "Country", name: "Lebanon" },
      },
      {
        "@type": "WebSite",
        "@id": `${siteUrl}/#website`,
        name: "Everbook",
        alternateName: "Everbook Album",
        url: `${siteUrl}/`,
        inLanguage: ["en", "fr"],
        publisher: { "@id": `${siteUrl}/#organization` },
      },
      ...products,
    ],
  };
}

writeFileSync(join(buildDir, "app.html"), template);
for (const lng of LANGUAGES) {
  for (const path of Object.keys(PUBLIC_PAGES)) {
    const address = localePath(path, lng);
    const file = address === "/" ? "index.html" : `${address.slice(1)}.html`;
    const out = pageHtml(path, lng, await render(path, lng), siteUrl ? await structuredData(path, siteUrl, lng) : []);
    mkdirSync(dirname(join(buildDir, file)), { recursive: true });
    writeFileSync(join(buildDir, file), out);
    console.log(`prerendered ${address} → build/${file}`);
  }
}
// For AI assistants (llmstxt.org): what Everbook is, its prices, its pages.
if (siteUrl) {
  writeFileSync(join(buildDir, "llms.txt"), await llms(siteUrl));
  console.log("wrote build/llms.txt");
}
rmSync(ssrDir, { recursive: true, force: true });
