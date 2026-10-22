import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { setLanguage } from "@/lib/i18n";
import { isPublicPage, localePath, splitLocale } from "@/lib/localePath";

const LANGUAGES = [
  { code: "en", label: "EN" },
  { code: "fr", label: "FR" },
];

// A manual pick here is what i18n.js's detection.caches (localStorage) is
// for: i18next.changeLanguage writes the new choice back to that same
// "everbook_lang" key itself, so it's automatically what gets read first
// on the next visit — nothing extra to persist here. On a public page, it
// also goes to that page's address in the new language (/faq ↔ /fr/faq).
export default function LanguageSwitcher({ className = "" }) {
  const { i18n } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const choose = async (code) => {
    await setLanguage(code);
    const { path } = splitLocale(location.pathname);
    if (isPublicPage(path)) navigate(localePath(path, code) + location.search + location.hash);
  };
  const current = i18n.language?.startsWith("fr") ? "fr" : "en";

  return (
    <div className={`inline-flex items-center text-xs font-medium tracking-wide ${className}`}>
      {LANGUAGES.map((lng, i) => (
        <React.Fragment key={lng.code}>
          {i > 0 && <span className="text-ink/60 px-1">/</span>}
          <button
            onClick={() => choose(lng.code)}
            aria-current={current === lng.code}
            className={
              current === lng.code
                ? "text-[color:var(--ink)]"
                : "text-ink/75 hover:text-[color:var(--ink)] transition-colors"
            }
          >
            {lng.label}
          </button>
        </React.Fragment>
      ))}
    </div>
  );
}
