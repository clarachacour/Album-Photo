// Runs after the two builds (package.json "build"): writes one HTML file per
// public page, holding its text, title and description.
//
//   build/index.html          the home page
//   build/faq.html, …         the other public pages (served at /faq… on
//                             Vercel thanks to "cleanUrls")
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

const { render, PUBLIC_PAGES } = await import(pathToFileURL(join(ssrDir, "prerender.js")).href);
const template = readFileSync(join(buildDir, "index.html"), "utf8");
const { siteUrl } = siteInfo();

const escapeAttr = (s) => s.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;");
const escapeText = (s) => s.replaceAll("&", "&amp;").replaceAll("<", "&lt;");

function setMeta(html, attr, name, content) {
  const re = new RegExp(`(<meta ${attr}="${name}" content=")[^"]*(")`);
  if (!re.test(html)) throw new Error(`index.html has no <meta ${attr}="${name}">`);
  return html.replace(re, `$1${escapeAttr(content)}$2`);
}

function pageHtml(path, { html, title, description }) {
  let out = template;
  if (!out.includes('<div id="root"></div>')) throw new Error('index.html has no empty <div id="root"></div>');
  out = out.replace('<div id="root"></div>', `<div id="root">${html}</div>`);
  // The page shows without JavaScript now: no "enable JavaScript" notice.
  out = out.replace(/\s*<noscript>[\s\S]*?<\/noscript>/, "");
  out = out.replace(/<title>[^<]*<\/title>/, `<title>${escapeText(title)}</title>`);
  out = setMeta(out, "name", "description", description);
  out = setMeta(out, "property", "og:title", title);
  out = setMeta(out, "property", "og:description", description);
  if (siteUrl) {
    const url = siteUrl + (path === "/" ? "/" : path);
    out = setMeta(out, "property", "og:url", url);
    out = out.replace("</head>", `  <link rel="canonical" href="${url}" />\n  </head>`);
  }
  return out;
}

writeFileSync(join(buildDir, "app.html"), template);
for (const path of Object.keys(PUBLIC_PAGES)) {
  const file = path === "/" ? "index.html" : `${path.slice(1)}.html`;
  const out = pageHtml(path, await render(path));
  mkdirSync(dirname(join(buildDir, file)), { recursive: true });
  writeFileSync(join(buildDir, file), out);
  console.log(`prerendered ${path} → build/${file}`);
}
rmSync(ssrDir, { recursive: true, force: true });
