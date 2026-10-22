import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

// Each language's texts are downloaded on their own, only when needed: a
// visitor gets their language, not both (about 100 KB each).
const LOADERS = {
  en: () => import("@/locales/en.json"),
  fr: () => import("@/locales/fr.json"),
};

export const LANGUAGES = Object.keys(LOADERS);

/** "fr", "fr-FR", "fr-CA"… → "fr"; anything else → "en". */
export const baseLanguage = (lng) => (String(lng || "").toLowerCase().startsWith("fr") ? "fr" : "en");

/** Downloads a language's texts (once). */
export async function loadLanguage(lng) {
  const code = baseLanguage(lng);
  if (!i18n.hasResourceBundle(code, "translation")) {
    const texts = await LOADERS[code]();
    i18n.addResourceBundle(code, "translation", texts.default || texts, true, true);
  }
  return code;
}

/** Switches the site's language, its texts downloaded first. */
export async function setLanguage(lng) {
  const code = await loadLanguage(lng);
  if (i18n.resolvedLanguage !== code) await i18n.changeLanguage(code);
  return code;
}

// Detection order: the address first (/fr/… is the French version of a
// public page); then a language the person explicitly picked before
// (stored under this same key by the switcher in TopNav.jsx), so a manual
// choice sticks on return visits; then, first visit, the browser's own
// language (`navigator.language` — "fr", "fr-FR", "en-US", etc.).
// Anything that isn't French resolves to English, since English is the
// language the whole app was originally written in.
i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {},
    partialBundledLanguages: true,
    fallbackLng: "en",
    supportedLngs: LANGUAGES,
    nonExplicitSupportedLngs: true, // "fr-FR", "fr-CA" etc. all resolve to "fr"
    detection: {
      order: ["path", "localStorage", "navigator"],
      lookupFromPathIndex: 0,
      caches: ["localStorage"],
      lookupLocalStorage: "everbook_lang",
    },
    interpolation: {
      escapeValue: false, // React already escapes — double-escaping would show literal &amp; etc.
    },
  });

/** Resolves once the visitor's language is ready (index.jsx waits for it). */
export const i18nReady = setLanguage(i18n.language);

// The page's language, for search engines and screen readers.
const setHtmlLang = (lng) => {
  // No document when the public pages are generated at build time.
  if (typeof document !== "undefined") document.documentElement.setAttribute("lang", baseLanguage(lng));
};
i18n.on("languageChanged", setHtmlLang);

export default i18n;
