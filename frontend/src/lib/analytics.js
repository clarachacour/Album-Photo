import { inject } from "@vercel/analytics";

// Pages that aren't visits: the print page (opened by the server to make
// the PDF), the printer's and the admin's pages.
const NOT_VISITS = /^\/(print|printer|admin)(\/|$)/;

/**
 * The visitors (Vercel Web Analytics, no cookies): pages seen and where the
 * visitors come from. Links only keep their utm_* tags (an ad's source):
 * the rest of a query can be a private key (an email's link).
 */
export function visitUrl(href) {
  const url = new URL(href);
  if (NOT_VISITS.test(url.pathname)) return null;
  const kept = new URLSearchParams();
  url.searchParams.forEach((value, key) => {
    if (key.startsWith("utm_")) kept.set(key, value);
  });
  url.search = kept.toString();
  url.hash = "";
  return url.toString();
}

export function initAnalytics() {
  inject({
    beforeSend: (event) => {
      const url = visitUrl(event.url);
      return url ? { ...event, url } : null;
    },
  });
}
