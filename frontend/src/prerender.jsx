// Generates the HTML of the public pages at build time (see
// scripts/prerender.mjs), so search engines and link previews (WhatsApp,
// Facebook…) get the page's text, title and description without running any
// JavaScript. In the browser, the site then draws the same page as usual.
import React from "react";
import { renderToString } from "react-dom/server";
import { StaticRouter } from "react-router";
import i18n from "@/lib/i18n";
import { AppRoutes } from "@/App";
import { faqData, llmsTxt, productData } from "@/lib/seoData";

// Address → key of its title and description in the locale files (meta.<key>).
export const PUBLIC_PAGES = {
  "/": "landing",
  "/faq": "faq",
  "/gift": "gift",
  "/contact": "contact",
  "/terms": "terms",
  "/privacy": "privacy",
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

/** schema.org data of a public page, besides the brand's (scripts/prerender.mjs). */
export async function structuredData(path, siteUrl) {
  await i18n.changeLanguage("en");
  if (path === "/") return productData(siteUrl);
  if (path === "/faq") return [faqData(siteUrl, i18n.t("faq.items", { returnObjects: true }))];
  return [];
}

/** llms.txt, in English. */
export async function llms(siteUrl) {
  await i18n.changeLanguage("en");
  return llmsTxt(siteUrl, i18n.t("faq.items", { returnObjects: true }));
}
