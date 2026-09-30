// Generates the HTML of the public pages at build time (see
// scripts/prerender.mjs), so search engines and link previews (WhatsApp,
// Facebook…) get the page's text, title and description without running any
// JavaScript. In the browser, the site then draws the same page as usual.
import React from "react";
import { renderToString } from "react-dom/server";
import { StaticRouter } from "react-router";
import i18n from "@/lib/i18n";
import { AppRoutes } from "@/App";

// Address → key of its title and description in the locale files (meta.<key>).
export const PUBLIC_PAGES = {
  "/": "landing",
  "/faq": "faq",
  "/contact": "contact",
  "/terms": "terms",
  "/privacy": "privacy",
  "/returns": "returns",
  "/shipping": "shipping",
};

/** { html, title, description } of a public page, in English. */
export async function render(path) {
  await i18n.changeLanguage("en");
  const page = PUBLIC_PAGES[path];
  const html = renderToString(
    <div className="App">
      <StaticRouter location={path}>
        <AppRoutes />
      </StaticRouter>
    </div>
  );
  const title = i18n.t(`meta.${page}.title`);
  return {
    html,
    // Same as usePageMeta.
    title: page === "landing" ? title : `${title} — Everbook`,
    description: i18n.t(`meta.${page}.description`, { defaultValue: i18n.t("meta.landing.description") }),
  };
}
