import React, { Suspense } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { TID } from "@/constants/testIds";
import { ArrowRight, Sparkles, BookOpen, Wand2, Images, ScanEye, ListChecks, Truck, Check, Undo2 } from "lucide-react";
import { usePageMeta } from "@/hooks/usePageMeta";
import { lazyPage } from "@/lib/lazyPage";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { PRICE_TABLE } from "@/lib/pricing";

// Cheapest album, for the "From $…" on the home page: follows the price table.
const FROM_PRICE = Math.min(...Object.values(PRICE_TABLE).flatMap((tiers) => Object.values(tiers)));

// Reloads the page once if its code can't be downloaded (a release since
// the page was opened, a dropped connection) — see lazyPage.
const TemplateGallery = lazyPage(() => import("@/components/landing/TemplateGallery"));

export default function Landing() {
  usePageMeta("landing");
  const navigate = useNavigate();
  const { t } = useTranslation();

  const handleCreateAlbumClick = () => {
    // On vérifie la présence de 'album_token' ou 'album_user'
    const isAuthenticated =
      localStorage.getItem("album_token") ||
      localStorage.getItem("album_user");

    if (isAuthenticated) {
      // Redirection vers le Dashboard si l'utilisateur est connecté
      navigate("/dashboard");
    } else {
      // Redirection vers la page de connexion sinon
      navigate("/auth");
    }
  };

  const processIcons = [<Wand2 size={22} />, <Sparkles size={22} />, <BookOpen size={22} />, <Truck size={22} />];
  const sortingIcons = [<Images size={20} />, <ScanEye size={20} />, <ListChecks size={20} />, <Undo2 size={20} />];

  return (
    <main className="min-h-screen bg-[color:var(--paper)]">
      {/* Hero — editorial asymmetry */}
      <section className="pt-32 md:pt-40 pb-24 md:pb-32 px-6 md:px-12">
        <div className="max-w-[1400px] mx-auto grid grid-cols-1 md:grid-cols-12 gap-8 md:gap-16 items-end">
          <div className="md:col-span-7 animate-fade-up">
            <h1
              className="font-serif-display leading-[0.92] tracking-tight text-[color:var(--ink)]"
              style={{ fontSize: "clamp(48px, 8vw, 128px)", fontWeight: 500 }}
            >
              {t("landing.hero.title_line1")}
              <br />
              <span className="italic text-[color:var(--coral)]">{t("landing.hero.title_highlight")}</span> {t("landing.hero.title_line2")}
            </h1>
            <p className="mt-8 text-lg md:text-xl text-[color:var(--ink)]/70 max-w-xl leading-relaxed font-sans">
              {t("landing.hero.subtitle")}
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-4">
              <button
                onClick={handleCreateAlbumClick}
                data-testid={TID.landingCta}
                className="group inline-flex items-center gap-3 bg-[color:var(--ink)] text-[color:var(--paper)] px-8 py-4 hover:bg-[color:var(--coral)] transition-colors duration-300"
              >
                <span className="text-sm font-semibold tracking-widest uppercase">{t("landing.hero.cta")}</span>
                <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
              </button>
            </div>
            <ul className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-sm text-[color:var(--ink)]/70" data-testid="landing-perks">
              {t("landing.hero.perks", { returnObjects: true, price: FROM_PRICE }).map((perk) => (
                <li key={perk} className="inline-flex items-center gap-1.5">
                  <Check size={14} className="text-[color:var(--coral)]" />
                  {perk}
                </li>
              ))}
            </ul>
          </div>

          {/* No fade-in here: this photo is the largest thing on screen, and
              it counts as displayed (for speed scores) only once fully shown. */}
          <div className="md:col-span-5">
            <div className="max-w-md mx-auto md:ml-auto">
              <img
                src="/hero-shelf.webp"
                alt={t("landing.hero.image_alt")}
                width={760}
                height={1024}
                fetchPriority="high"
                className="w-full h-auto rounded-sm book-shadow"
              />
            </div>
          </div>
        </div>
      </section>

      {/* Process strip */}
      <section className="border-y border-[color:var(--border-soft)] py-16 md:py-24 bg-white">
        <div className="max-w-[1400px] mx-auto px-6 md:px-12 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-12">
          {t("landing.process.steps", { returnObjects: true }).map((s, i) => (
            <div key={i} className="flex gap-6 items-start">
              <div className="font-serif-display text-4xl text-[color:var(--coral)]">{String(i + 1).padStart(2, "0")}</div>
              <div>
                <div className="flex items-center gap-2 text-[color:var(--ink)] mb-2">
                  {processIcons[i]}
                  <h3 className="font-serif-display text-2xl">{s.title}</h3>
                </div>
                <p className="text-[color:var(--ink)]/70 leading-relaxed">{s.body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* How the sorting works: a short title beside four short points */}
      <section className="py-14 md:py-20 px-6 md:px-12">
        <div className="max-w-[1400px] mx-auto grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-16 items-center">
          <div className="lg:col-span-4">
            <div className="eyebrow mb-3">{t("landing.sorting.eyebrow")}</div>
            <h2 className="font-serif-display text-3xl md:text-4xl tracking-tight leading-[1.05] mb-4">
              {t("landing.sorting.title_line1")}<br />
              <em className="not-italic text-[color:var(--muted)]">{t("landing.sorting.title_highlight")}</em>
            </h2>
            <p className="text-[color:var(--ink)]/70 leading-relaxed">
              {t("landing.sorting.intro")}
            </p>
          </div>

          <div className="lg:col-span-8 grid grid-cols-1 sm:grid-cols-2 gap-x-10 gap-y-6">
            {t("landing.sorting.steps", { returnObjects: true }).map((s, i) => (
              <div key={i} className="flex gap-4 items-start">
                <div className="mt-0.5 text-[color:var(--coral)] shrink-0">{sortingIcons[i]}</div>
                <div>
                  <h3 className="font-serif-display text-lg mb-1">{s.title}</h3>
                  <p className="text-[color:var(--ink)]/70 leading-relaxed text-sm">{s.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Theme showcase */}
      <section id="templates" className="py-24 md:py-32 px-6 md:px-12">
        <div className="max-w-[1400px] mx-auto">
          <div className="max-w-2xl mb-16">
            <div className="eyebrow mb-4">{t("landing.templates.eyebrow")}</div>
            <h2 className="font-serif-display text-4xl md:text-6xl tracking-tight leading-[1] mb-6">
              {t("landing.templates.title_line1")}<br />
              <em className="not-italic text-[color:var(--muted)]">{t("landing.templates.title_highlight")}</em>
            </h2>
            <p className="text-[color:var(--ink)]/70">
              {t("landing.templates.intro")}
            </p>
          </div>

          {/* Loaded after the first paint: the templates list (with the
              cover logos) is a large file the top of the page doesn't need. */}
          {/* If it still can't load, the rest of the page stays usable. */}
          <ErrorBoundary renderFallback={() => null}>
            <Suspense fallback={<div className="min-h-[600px]" />}>
              <TemplateGallery />
            </Suspense>
          </ErrorBoundary>
        </div>
      </section>

      {/* Footer CTA */}
      <section className="py-24 md:py-32 px-6 md:px-12 bg-[color:var(--ink)] text-[color:var(--paper)]">
        <div className="max-w-[1400px] mx-auto flex flex-col md:flex-row items-end justify-between gap-8">
          <h2 className="font-serif-display text-5xl md:text-7xl leading-[0.95] max-w-4xl">
            {t("landing.footer.title_line1")}<br />{t("landing.footer.title_line2")}
          </h2>
          <button
            onClick={handleCreateAlbumClick}
            className="inline-flex items-center gap-3 bg-[color:var(--coral)] text-[color:var(--ink)] px-8 py-4 hover:bg-[color:var(--paper)] transition-colors duration-300"
            data-testid="footer-cta"
          >
            <span className="text-sm font-semibold tracking-widest uppercase">{t("landing.footer.cta")}</span>
            <ArrowRight size={16} />
          </button>
        </div>
      </section>
    </main>
  );
}
