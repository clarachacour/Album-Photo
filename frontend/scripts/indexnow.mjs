// IndexNow (indexnow.org): tells Bing (and the other search engines that
// share it) which public pages changed, right after a production build,
// instead of waiting for them to come back. Nothing runs on the site
// itself: only this message, sent by the build.
//
// The key is not a secret: search engines check it at
// https://<site>/<key>.txt (public/<key>.txt) to be sure the message
// comes from the site's owner.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const ENDPOINT = "https://api.indexnow.org/indexnow";
const TIMEOUT_MS = 8000;

export function indexNowKey(publicDir) {
  const file = readdirSync(publicDir).find((f) => /^[0-9a-f]{32}\.txt$/.test(f));
  return file ? readFileSync(join(publicDir, file), "utf8").trim() : null;
}

// What a page says, without what changes at every build (file names of
// the scripts and styles).
const content = (html) => html.replace(/\/assets\/[^"' )]+/g, "").replace(/\s+/g, " ");

async function fetchText(url) {
  const res = await fetch(url, { signal: AbortSignal.timeout(TIMEOUT_MS), redirect: "manual" });
  return res.ok ? res.text() : null;
}

/** pages: [{ url, html }] — the new version of each public page. Sends the
 *  ones that differ from what the live site shows (all of them if it can't
 *  be read). Never fails the build: a problem is only logged. */
export async function notifyIndexNow({ siteUrl, key, pages }) {
  if (!key) return console.warn("IndexNow: no key file in public/, nothing sent");
  try {
    const changed = [];
    for (const { url, html } of pages) {
      const live = await fetchText(url).catch(() => null);
      if (!live || content(live) !== content(html)) changed.push(url);
    }
    if (!changed.length) return console.log("IndexNow: no public page changed, nothing sent");
    const res = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: JSON.stringify({ host: new URL(siteUrl).host, key, keyLocation: `${siteUrl}/${key}.txt`, urlList: changed }),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    console.log(`IndexNow: ${changed.length} page(s) sent, answer ${res.status}`);
  } catch (e) {
    console.warn(`IndexNow: not sent (${e.message})`);
  }
}
