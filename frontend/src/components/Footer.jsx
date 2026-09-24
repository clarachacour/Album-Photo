import React from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export default function Footer() {
  const { t } = useTranslation();
  const year = new Date().getFullYear();

  return (
    <footer className="bg-[color:var(--ink)] text-[color:var(--paper)]">
      <div className="max-w-[1400px] mx-auto px-6 md:px-12 py-16 grid grid-cols-2 md:grid-cols-4 gap-10">
        <div className="col-span-2 md:col-span-1">
          <span className="font-serif-display text-2xl tracking-tight">Everbook</span>
          <p className="mt-3 text-sm text-[color:var(--paper)]/60 max-w-[220px]">
            {t("footer.tagline")}
          </p>
        </div>

        <div>
          <div className="eyebrow mb-4 text-[color:var(--paper)]/50">{t("footer.navigation")}</div>
          <ul className="space-y-2.5 text-sm">
            <li><Link to="/dashboard" className="hover:text-[color:var(--coral)] transition-colors">{t("nav.myAlbums")}</Link></li>
            <li><Link to="/orders" className="hover:text-[color:var(--coral)] transition-colors">{t("nav.orders")}</Link></li>
            <li><Link to="/faq" className="hover:text-[color:var(--coral)] transition-colors">{t("nav.faq")}</Link></li>
            <li><Link to="/contact" className="hover:text-[color:var(--coral)] transition-colors">{t("footer.contact")}</Link></li>
          </ul>
        </div>

        <div>
          <div className="eyebrow mb-4 text-[color:var(--paper)]/50">{t("footer.legal")}</div>
          <ul className="space-y-2.5 text-sm">
            <li><Link to="/terms" className="hover:text-[color:var(--coral)] transition-colors">{t("footer.terms")}</Link></li>
            <li><Link to="/privacy" className="hover:text-[color:var(--coral)] transition-colors">{t("footer.privacy")}</Link></li>
            <li><Link to="/returns" className="hover:text-[color:var(--coral)] transition-colors">{t("footer.returns")}</Link></li>
            <li><Link to="/shipping" className="hover:text-[color:var(--coral)] transition-colors">{t("footer.shipping")}</Link></li>
          </ul>
        </div>

        <div>
          <div className="eyebrow mb-4 text-[color:var(--paper)]/50">{t("footer.company")}</div>
          <ul className="space-y-2.5 text-sm text-[color:var(--paper)]/60">
            {/* Placeholders — replace with the real registered name, RC
                number/jurisdiction, and address once confirmed; nothing
                here should be invented on the business's behalf. */}
            <li>{t("footer.legalNamePlaceholder")}</li>
            <li>{t("footer.rcPlaceholder")}</li>
            <li>{t("footer.addressPlaceholder")}</li>
          </ul>
        </div>
      </div>

      <div className="border-t border-[color:var(--paper)]/10">
        <div className="max-w-[1400px] mx-auto px-6 md:px-12 py-6 flex flex-col md:flex-row items-center justify-between gap-2 text-xs text-[color:var(--paper)]/50">
          <span>© {year} Everbook. {t("footer.rightsReserved")}</span>
          <span>{t("footer.madeIn")}</span>
        </div>
      </div>
    </footer>
  );
}
