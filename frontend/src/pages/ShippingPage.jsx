import React from "react";
import { useTranslation } from "react-i18next";

export default function ShippingPage() {
  const { t } = useTranslation();
  const sections = t("legal.shipping.sections", { returnObjects: true });
  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
      <div className="max-w-[800px] mx-auto">
        <div className="eyebrow mb-3">{t("legal.shipping.eyebrow")}</div>
        <h1 className="font-serif-display text-4xl md:text-5xl tracking-tight mb-4">{t("legal.shipping.title")}</h1>
        <p className="text-sm text-[color:var(--muted)] mb-12">{t("legal.lastUpdated")}</p>
        <div className="space-y-8">
          {sections.map((s, i) => (
            <div key={i}>
              <h2 className="font-serif-display text-xl mb-2">{s.heading}</h2>
              <p className="text-sm text-[color:var(--ink)]/70 leading-relaxed whitespace-pre-line">{s.body}</p>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
