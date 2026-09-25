import React from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

/** Shown for any address that doesn't match a page of the site. */
export default function NotFound() {
  const { t } = useTranslation();
  return (
    <main className="min-h-[70vh] flex items-center justify-center p-8 bg-[color:var(--paper)]" data-testid="not-found">
      <div className="w-full max-w-md text-center">
        <p className="eyebrow text-[color:var(--coral)] mb-4">404</p>
        <h1 className="font-serif-display text-4xl tracking-tight mb-3">{t("notFound.title")}</h1>
        <p className="text-[color:var(--ink)]/70 mb-8">{t("notFound.body")}</p>
        <Link
          to="/"
          className="inline-flex items-center justify-center bg-[color:var(--ink)] text-[color:var(--paper)] px-8 py-3 hover:bg-[color:var(--coral)] transition-colors"
        >
          <span className="text-sm font-semibold tracking-widest uppercase">{t("notFound.home")}</span>
        </Link>
      </div>
    </main>
  );
}
