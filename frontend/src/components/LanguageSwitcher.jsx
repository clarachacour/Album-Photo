import React from "react";
import { useTranslation } from "react-i18next";

const LANGUAGES = [
  { code: "en", label: "EN" },
  { code: "fr", label: "FR" },
];

// A manual pick here is what i18n.js's detection.caches (localStorage) is
// for: i18next.changeLanguage writes the new choice back to that same
// "everbook_lang" key itself, so it's automatically what gets read first
// on the next visit — nothing extra to persist here.
export default function LanguageSwitcher({ className = "" }) {
  const { i18n } = useTranslation();
  const current = i18n.language?.startsWith("fr") ? "fr" : "en";

  return (
    <div className={`inline-flex items-center text-xs font-medium tracking-wide ${className}`}>
      {LANGUAGES.map((lng, i) => (
        <React.Fragment key={lng.code}>
          {i > 0 && <span className="text-[color:var(--ink)]/30 px-1">/</span>}
          <button
            onClick={() => i18n.changeLanguage(lng.code)}
            aria-current={current === lng.code}
            className={
              current === lng.code
                ? "text-[color:var(--ink)]"
                : "text-[color:var(--ink)]/50 hover:text-[color:var(--ink)] transition-colors"
            }
          >
            {lng.label}
          </button>
        </React.Fragment>
      ))}
    </div>
  );
}
