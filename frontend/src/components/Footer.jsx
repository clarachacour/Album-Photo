import React from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useLocalePath } from "@/components/LocalLink";
import { Instagram } from "lucide-react";
import { OCCASIONS } from "@/lib/occasions";

// The brand's accounts (also declared to search engines, see scripts/prerender.mjs).
export const INSTAGRAM_URL = "https://www.instagram.com/everbook_album/";

export default function Footer() {
  const { t } = useTranslation();
  const lp = useLocalePath();
  const year = new Date().getFullYear();

  return (
    <footer className="bg-[color:var(--ink)] text-[color:var(--paper)]">
      <div className="max-w-[1400px] mx-auto px-6 md:px-12 py-16 grid grid-cols-2 md:grid-cols-5 gap-10">
        <div className="col-span-2 md:col-span-1">
          <span className="font-serif-display text-2xl tracking-tight">Everbook</span>
          <p className="mt-3 text-sm text-paper/60 max-w-[220px]">
            {t("footer.tagline")}
          </p>
        </div>

        <div>
          <div className="eyebrow mb-4 text-paper/70">{t("footer.navigation")}</div>
          <ul className="space-y-2.5 text-sm">
            <li><Link to="/dashboard" className="hover:text-[color:var(--coral)] transition-colors">{t("nav.myAlbums")}</Link></li>
            <li><Link to="/orders" className="hover:text-[color:var(--coral)] transition-colors">{t("nav.orders")}</Link></li>
            <li><Link to={lp("/gift")} className="hover:text-[color:var(--coral)] transition-colors">{t("nav.gift")}</Link></li>
            <li><Link to={lp("/faq")} className="hover:text-[color:var(--coral)] transition-colors">{t("nav.faq")}</Link></li>
            <li><Link to={lp("/contact")} className="hover:text-[color:var(--coral)] transition-colors">{t("footer.contact")}</Link></li>
          </ul>
        </div>

        <div>
          <div className="eyebrow mb-4 text-paper/70">{t("footer.albums")}</div>
          <ul className="space-y-2.5 text-sm">
            {Object.entries(OCCASIONS).map(([name, o]) => (
              <li key={name}><Link to={lp(o.path)} className="hover:text-[color:var(--coral)] transition-colors">{t(`occasions.${name}.linkLabel`)}</Link></li>
            ))}
          </ul>
        </div>

        <div>
          <div className="eyebrow mb-4 text-paper/70">{t("footer.legal")}</div>
          <ul className="space-y-2.5 text-sm">
            <li><Link to={lp("/terms")} className="hover:text-[color:var(--coral)] transition-colors">{t("footer.terms")}</Link></li>
            <li><Link to={lp("/privacy")} className="hover:text-[color:var(--coral)] transition-colors">{t("footer.privacy")}</Link></li>
            <li><Link to={lp("/shipping")} className="hover:text-[color:var(--coral)] transition-colors">{t("footer.shipping")}</Link></li>
          </ul>
        </div>

        <div>
          <div className="eyebrow mb-4 text-paper/70">{t("footer.company")}</div>
          <ul className="space-y-2.5 text-sm text-paper/60">
            <li>{t("footer.legalName")}</li>
            <li>
              <a href={`mailto:${t("footer.email")}`} className="hover:text-[color:var(--coral)] transition-colors">
                {t("footer.email")}
              </a>
            </li>
            <li>
              <a href={INSTAGRAM_URL} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 hover:text-[color:var(--coral)] transition-colors" data-testid="footer-instagram">
                <Instagram size={15} /> @everbook_album
              </a>
            </li>
          </ul>
        </div>
      </div>

      <div className="border-t border-paper/10">
        <div className="max-w-[1400px] mx-auto px-6 md:px-12 py-6 flex flex-col md:flex-row items-center justify-between gap-2 text-xs text-paper/70">
          <span>© {year} Everbook. {t("footer.rightsReserved")}</span>
          <span>{t("footer.madeIn")}</span>
        </div>
      </div>
    </footer>
  );
}
