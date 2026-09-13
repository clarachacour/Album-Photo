import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronDown } from "lucide-react";

export default function FAQPage() {
  const [openIdx, setOpenIdx] = useState(null);
  const { t } = useTranslation();
  const faqs = t("faq.items", { returnObjects: true });

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
      <div className="max-w-[800px] mx-auto">
        <div className="mb-16">
          <div className="eyebrow mb-3">{t("faq.eyebrow")}</div>
          <h1 className="font-serif-display text-5xl md:text-6xl tracking-tight mb-4">{t("faq.title")}</h1>
          <p className="text-sm text-[color:var(--muted)]">
            {t("faq.cantFind")}{" "}
            <Link to="/contact" className="underline text-[color:var(--ink)]">
              {t("faq.getInTouch")}
            </Link>
            .
          </p>
        </div>

        <div className="divide-y divide-[color:var(--border-soft)] border-t border-b border-[color:var(--border-soft)]">
          {faqs.map((item, i) => (
            <div key={i}>
              <button
                onClick={() => setOpenIdx(openIdx === i ? null : i)}
                className="w-full flex items-center justify-between gap-4 py-6 text-left"
                data-testid={`faq-question-${i}`}
              >
                <span className="font-serif-display text-lg md:text-xl tracking-tight">{item.q}</span>
                <ChevronDown
                  size={18}
                  className={`shrink-0 transition-transform ${openIdx === i ? "rotate-180" : ""}`}
                />
              </button>
              {openIdx === i && (
                <p className="text-sm text-[color:var(--ink)]/70 leading-relaxed pb-6 pr-8">{item.a}</p>
              )}
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
