import React from "react";
import { useTranslation } from "react-i18next";
import { ArrowRight } from "lucide-react";
import { usePageMeta } from "@/hooks/usePageMeta";
import LocalLink from "@/components/LocalLink";
import { SignupLink } from "@/components/SignupLink";
import { DIGITAL_PRICE, MAX_ALBUM_PAGES, ONLINE_PAYMENT, OVERAGE_FROM, OVERAGE_PER_PAGE, PAGE_TIERS, PRICE_TABLE, SHIPPING_PRICE } from "@/lib/pricing";

const SIZES = ["A5", "A4"];

/** The albums' prices, from the same price table as the order page and the
 * data given to search engines (lib/seoData.js), so they always agree. */
export default function PricingPage() {
  usePageMeta("pricing");
  const { t, i18n } = useTranslation();
  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
      <div className="max-w-[800px] mx-auto">
        <div className="eyebrow mb-3">{t("pricing.eyebrow")}</div>
        <h1 className="font-serif-display text-4xl md:text-5xl tracking-tight mb-4">{t("pricing.title")}</h1>
        <p className="text-ink/70 mb-10">{t("pricing.intro")}</p>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-t border-b border-[color:var(--border-soft)]" data-testid="pricing-table">
            <caption className="sr-only">{t("pricing.caption")}</caption>
            <thead>
              <tr className="border-b border-[color:var(--border-soft)]">
                <th scope="col" className="py-4 pr-4 eyebrow font-normal">{t("pricing.pages")}</th>
                {SIZES.map((size) => (
                  <th key={size} scope="col" className="py-4 pr-4 eyebrow font-normal">{t(`pricing.size${size}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {PAGE_TIERS.map((pages) => (
                <tr key={pages} className="border-b border-[color:var(--border-soft)] last:border-b-0">
                  <th scope="row" className="py-4 pr-4 font-medium">{t("pricing.pageCount", { pages })}</th>
                  {SIZES.map((size) => (
                    <td key={size} className="py-4 pr-4 font-serif-display text-2xl">{t("pricing.price", { price: PRICE_TABLE[size][pages] })}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-10 space-y-6 text-sm text-ink/70 leading-relaxed">
          <div>
            <h2 className="font-serif-display text-xl text-[color:var(--ink)] mb-2">{t("pricing.pagesTitle")}</h2>
            <p>{t("pricing.pagesBody", { from: OVERAGE_FROM, perPage: OVERAGE_PER_PAGE.toLocaleString(i18n.resolvedLanguage, { minimumFractionDigits: 2 }), max: MAX_ALBUM_PAGES })}</p>
          </div>
          <div>
            <h2 className="font-serif-display text-xl text-[color:var(--ink)] mb-2">{t("pricing.deliveryTitle")}</h2>
            <p>
              {t("pricing.deliveryBody", { price: SHIPPING_PRICE })}{" "}
              <LocalLink to="/shipping" className="underline hover:text-[color:var(--ink)]">{t("pricing.deliveryLink")}</LocalLink>
            </p>
          </div>
          <div>
            <h2 className="font-serif-display text-xl text-[color:var(--ink)] mb-2">{t("pricing.pdfTitle")}</h2>
            <p>{t(ONLINE_PAYMENT ? "pricing.pdfBody" : "pricing.pdfSoon", { price: DIGITAL_PRICE })}</p>
          </div>
          <div>
            <h2 className="font-serif-display text-xl text-[color:var(--ink)] mb-2">{t("pricing.paymentTitle")}</h2>
            <p>{t(ONLINE_PAYMENT ? "pricing.paymentOnline" : "pricing.paymentCash")}</p>
          </div>
        </div>

        <div className="mt-12 flex flex-wrap items-center gap-6">
          <SignupLink
            className="group inline-flex items-center gap-3 bg-[color:var(--ink)] text-[color:var(--paper)] px-8 py-4 hover:bg-[color:var(--coral)] transition-colors duration-300"
            data-testid="pricing-cta"
          >
            <span className="text-sm font-semibold tracking-widest uppercase">{t("landing.hero.cta")}</span>
            <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
          </SignupLink>
          <LocalLink to="/faq" className="text-sm underline text-ink/70 hover:text-[color:var(--ink)]">{t("pricing.faqLink")}</LocalLink>
        </div>
      </div>
    </main>
  );
}
