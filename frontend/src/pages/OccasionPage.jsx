import React from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight, Check } from "lucide-react";
import { usePageMeta } from "@/hooks/usePageMeta";
import LocalLink from "@/components/LocalLink";
import { OCCASIONS } from "@/lib/occasions";

const isSignedIn = () => {
  try {
    return Boolean(localStorage.getItem("album_token") || localStorage.getItem("album_user"));
  } catch {
    return false;
  }
};

export default function OccasionPage({ occasion }) {
  usePageMeta(`occasion_${occasion}`);
  const navigate = useNavigate();
  const { t } = useTranslation();
  const k = (key, opts) => t(`occasions.${occasion}.${key}`, opts);
  const { covers } = OCCASIONS[occasion];
  const others = Object.entries(OCCASIONS).filter(([name]) => name !== occasion);
  const start = () => navigate(isSignedIn() ? "/dashboard" : "/auth");

  const cta = (
    <button
      onClick={start}
      className="group inline-flex items-center gap-3 bg-[color:var(--ink)] text-[color:var(--paper)] px-8 py-4 hover:bg-[color:var(--coral)] transition-colors duration-300"
      data-testid="occasion-cta"
    >
      <span className="text-sm font-semibold tracking-widest uppercase">{t("landing.hero.cta")}</span>
      <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
    </button>
  );

  return (
    <main className="min-h-screen bg-[color:var(--paper)]">
      <section className="pt-32 md:pt-40 pb-16 md:pb-24 px-6 md:px-12">
        <div className="max-w-[1100px] mx-auto">
          <div className="eyebrow mb-4">{k("eyebrow")}</div>
          <h1 className="font-serif-display text-5xl md:text-7xl tracking-tight leading-[0.95] max-w-3xl">{k("title")}</h1>
          <p className="mt-8 text-lg md:text-xl text-ink/70 max-w-2xl leading-relaxed">{k("intro")}</p>
          <div className="mt-10">{cta}</div>
        </div>
      </section>

      <section className="pb-16 md:pb-24 px-6 md:px-12" aria-label={k("coversLabel")}>
        <div className="max-w-[1100px] mx-auto grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6">
          {covers.map(([src, name]) => (
            <figure key={src} className="bg-white">
              <img src={src} alt={k("coverAlt", { name })} width={480} height={640} loading="lazy" decoding="async" className="w-full h-auto" />
              <figcaption className="text-center text-xs py-2 text-ink/80">{name}</figcaption>
            </figure>
          ))}
        </div>
      </section>

      <section className="py-16 md:py-24 px-6 md:px-12 bg-white border-y border-[color:var(--border-soft)]">
        <div className="max-w-[1100px] mx-auto grid grid-cols-1 md:grid-cols-3 gap-10">
          {k("points", { returnObjects: true }).map((p) => (
            <div key={p.title}>
              <h2 className="font-serif-display text-2xl mb-3 flex items-start gap-2">
                <Check size={18} className="text-[color:var(--coral)] mt-1.5 shrink-0" />
                {p.title}
              </h2>
              <p className="text-sm text-ink/75 leading-relaxed">{p.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="py-16 md:py-24 px-6 md:px-12">
        <div className="max-w-[1100px] mx-auto">
          <h2 className="font-serif-display text-3xl md:text-4xl tracking-tight mb-10">{t("occasions.howTitle")}</h2>
          <ol className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-8">
            {t("landing.process.steps", { returnObjects: true }).map((s, i) => (
              <li key={s.title}>
                <div className="font-serif-display text-3xl text-[color:var(--coral)]">{String(i + 1).padStart(2, "0")}</div>
                <h3 className="font-serif-display text-xl mt-2 mb-1">{s.title}</h3>
                <p className="text-sm text-ink/75 leading-relaxed">{s.body}</p>
              </li>
            ))}
          </ol>
          <p className="mt-12 text-sm text-ink/75">
            {t("occasions.giftLine")}{" "}
            <LocalLink to="/gift" className="underline text-[color:var(--ink)]">{t("nav.gift")}</LocalLink>
          </p>
          <div className="mt-10">{cta}</div>
        </div>
      </section>

      <nav className="pb-24 px-6 md:px-12" aria-label={t("occasions.moreLabel")}>
        <div className="max-w-[1100px] mx-auto border-t border-[color:var(--border-soft)] pt-10">
          <div className="eyebrow mb-4">{t("occasions.moreLabel")}</div>
          <ul className="flex flex-wrap gap-x-8 gap-y-3">
            {others.map(([name, o]) => (
              <li key={name}>
                <LocalLink to={o.path} className="font-serif-display text-xl underline-offset-4 hover:underline">
                  {t(`occasions.${name}.linkLabel`)}
                </LocalLink>
              </li>
            ))}
            <li>
              <LocalLink to="/faq" className="font-serif-display text-xl underline-offset-4 hover:underline">{t("nav.faq")}</LocalLink>
            </li>
          </ul>
        </div>
      </nav>
    </main>
  );
}
