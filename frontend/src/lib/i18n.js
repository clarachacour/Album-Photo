import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

import en from "@/locales/en.json";
import fr from "@/locales/fr.json";

// Detection order: a language the person explicitly picked before (stored
// under this same key by the switcher in TopNav.jsx) always wins on
// return visits: it overrides whatever the browser reports, exactly the
// "auto-detect, but a manual choice sticks" behavior asked for. First
// visit, with nothing stored yet, falls through to the browser's own
// language (`navigator.language` — "fr", "fr-FR", "en-US", etc.).
// Anything that isn't French resolves to English, since English is the
// language the whole app was originally written in.
i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      fr: { translation: fr },
    },
    fallbackLng: "en",
    supportedLngs: ["en", "fr"],
    nonExplicitSupportedLngs: true, // "fr-FR", "fr-CA" etc. all resolve to "fr"
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
      lookupLocalStorage: "everbook_lang",
    },
    interpolation: {
      escapeValue: false, // React already escapes — double-escaping would show literal &amp; etc.
    },
  });

// The page's language, for search engines and screen readers.
const setHtmlLang = (lng) => {
  // No document when the public pages are generated at build time.
  if (typeof document !== "undefined") document.documentElement.setAttribute("lang", (lng || "en").slice(0, 2));
};
setHtmlLang(i18n.resolvedLanguage);
i18n.on("languageChanged", setHtmlLang);

export default i18n;
