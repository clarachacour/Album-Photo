// The public pages exist in two versions, each at its own address, so
// search engines can show the right one: English at /faq, French at
// /fr/faq. The app's other pages (albums, cart, orders…) have one address,
// in the language the visitor chose.
//
// No "@/" import here: seo.plugin.js (the sitemap) reads this file too.

/** The public pages, in English (their French version is under /fr). */
export const PUBLIC_PAGES = [
  "/",
  "/gift",
  "/faq",
  "/travel-photo-book",
  "/couple-photo-album",
  "/family-photo-album",
  "/contact",
  "/shipping",
  "/terms",
  "/privacy",
];

const PREFIX = { fr: "/fr" };

/** "/fr/faq" → { lng: "fr", path: "/faq" }; "/faq" → { lng: null, path: "/faq" }. */
export function splitLocale(pathname) {
  for (const [lng, prefix] of Object.entries(PREFIX)) {
    if (pathname === prefix || pathname.startsWith(prefix + "/")) {
      return { lng, path: pathname.slice(prefix.length) || "/" };
    }
  }
  return { lng: null, path: pathname };
}

export const isPublicPage = (path) => PUBLIC_PAGES.includes(path);

/** A page's address in a language: "/faq" in French → "/fr/faq" (public
 *  pages only; any other address stays as is). Keeps "?…" and "#…". */
export function localePath(to, lng) {
  const match = /^([^?#]*)(.*)$/.exec(to);
  const path = splitLocale(match[1] || "/").path;
  const prefix = PREFIX[String(lng || "").slice(0, 2)];
  if (!prefix || !isPublicPage(path)) return path + match[2];
  return (path === "/" ? prefix : prefix + path) + match[2];
}
