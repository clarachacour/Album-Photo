import { useEffect } from "react";
import { useTranslation } from "react-i18next";

/**
 * Sets the browser tab title and the search-engine description of the
 * current page, in the visitor's language, from the locale files:
 * meta.<page>.title and meta.<page>.description.
 */
export function usePageMeta(page) {
  const { t, i18n } = useTranslation();
  useEffect(() => {
    const title = t(`meta.${page}.title`);
    document.title = page === "landing" ? title : `${title} — Everbook`;
    // Pages without their own description use the site's.
    const description = t(`meta.${page}.description`, { defaultValue: t("meta.landing.description") });
    const tag = document.querySelector('meta[name="description"]');
    if (tag) tag.setAttribute("content", description);
  }, [page, t, i18n.language]);
}
