// Generates the HTML of the public pages at build time (see
// scripts/prerender.mjs), so search engines and link previews (WhatsApp,
// Facebook…) get the page's text, title and description without running any
// JavaScript. In the browser, the site then draws the same page as usual.
// Each page exists in English and, under /fr, in French (lib/localePath.js).
import React from "react";
import { Buffer } from "node:buffer";
import { prerenderToNodeStream } from "react-dom/static";
import { StaticRouter } from "react-router";
import i18n, { LANGUAGES, loadLanguage } from "@/lib/i18n";
import { localePath } from "@/lib/localePath";
import { AppRoutes } from "@/App";
import { faqData, llmsTxt, productData } from "@/lib/seoData";
import { PRICE_TEXT } from "@/lib/pricing";

// Address (in English) → key of its title and description in the locale
// files (meta.<key>). Every page of lib/localePath.js's PUBLIC_PAGES.
export const PUBLIC_PAGES = {
  "/": "landing",
  "/faq": "faq",
  "/gift": "gift",
  "/travel-photo-book": "occasion_travel",
  "/couple-photo-album": "occasion_couple",
  "/family-photo-album": "occasion_family",
  "/contact": "contact",
  "/terms": "terms",
  "/privacy": "privacy",
  "/shipping": "shipping",
  "/pricing": "pricing",
};

export { LANGUAGES, localePath };

async function speak(lng) {
  await loadLanguage(lng);
  await i18n.changeLanguage(lng);
}

/** The page's HTML once everything it loads on demand is there (the home
 * page's templates gallery…): prerenderToNodeStream waits for every
 * Suspense to be ready, where renderToString wrote their placeholder (the
 * English home page, drawn first, had no gallery). */
async function pageMarkup(element) {
  const { prelude } = await prerenderToNodeStream(element);
  // Joined as bytes: a character (é…) can be cut between two chunks.
  const chunks = [];
  for await (const chunk of prelude) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks).toString("utf8");
}

/** { html, title, description } of a public page, in a language. */
export async function render(path, lng = "en") {
  await speak(lng);
  const page = PUBLIC_PAGES[path];
  const html = await pageMarkup(
    <div className="App">
      <StaticRouter location={localePath(path, lng)}>
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
export async function structuredData(path, siteUrl, lng = "en") {
  await speak(lng);
  if (path === "/pricing") return [{ "@context": "https://schema.org", "@graph": productData(siteUrl, lng) }];
  if (path === "/faq") return [faqData(siteUrl, i18n.t("faq.items", { ...PRICE_TEXT, returnObjects: true }), siteUrl + localePath("/faq", lng))];
  return [];
}

/** llms.txt, in English. */
export async function llms(siteUrl) {
  await speak("en");
  return llmsTxt(siteUrl, i18n.t("faq.items", { ...PRICE_TEXT, returnObjects: true }));
}
