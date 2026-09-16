import React from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { COVER_THEMES } from "@/lib/coverThemes";
import { TID } from "@/constants/testIds";
import { ArrowRight, Sparkles, BookOpen, Wand2, Images, ScanEye, ListChecks } from "lucide-react";

export default function Landing() {
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

  const processIcons = [<Wand2 size={22} />, <Sparkles size={22} />, <BookOpen size={22} />];
  const sortingIcons = [<Images size={20} />, <ScanEye size={20} />, <Sparkles size={20} />, <ListChecks size={20} />];

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
          </div>

          <div className="md:col-span-5 animate-fade-up" style={{ animationDelay: "0.15s" }}>
            <div className="max-w-md mx-auto md:ml-auto">
              <img
                src="/hero-shelf.jpg"
                alt="Printed photo albums on a shelf"
                className="w-full h-auto rounded-sm book-shadow"
              />
            </div>
          </div>
        </div>
      </section>

      {/* Process strip */}
      <section className="border-y border-[color:var(--border-soft)] py-16 md:py-24 bg-white">
        <div className="max-w-[1400px] mx-auto px-6 md:px-12 grid grid-cols-1 md:grid-cols-3 gap-12">
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

      {/* How the sorting actually works */}
      <section className="py-24 md:py-32 px-6 md:px-12">
        <div className="max-w-[1400px] mx-auto">
          <div className="max-w-2xl mb-16">
            <div className="eyebrow mb-4">{t("landing.sorting.eyebrow")}</div>
            <h2 className="font-serif-display text-4xl md:text-6xl tracking-tight leading-[1] mb-6">
              {t("landing.sorting.title_line1")}<br />
              <em className="not-italic text-[color:var(--muted)]">{t("landing.sorting.title_highlight")}</em>
            </h2>
            <p className="text-[color:var(--ink)]/70 leading-relaxed">
              {t("landing.sorting.intro")}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-14">
            {t("landing.sorting.steps", { returnObjects: true }).map((s, i) => (
              <div key={i} className="flex gap-5 items-start">
                <div className="mt-1 text-[color:var(--coral)] shrink-0">{sortingIcons[i]}</div>
                <div>
                  <h3 className="font-serif-display text-xl mb-2">{s.title}</h3>
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

          {COVER_THEMES.map((theme) => (
            <div key={theme.id} className="mb-14">
              <h3 className="font-serif-display text-2xl mb-5">{theme.label}</h3>
              <div className="flex gap-4 overflow-x-auto pb-2">
                {theme.templates.map((tpl) => (
                  <div key={tpl.id} className="shrink-0 w-40 md:w-48">
                    <div className="aspect-[3/4] overflow-hidden book-shadow rounded-sm">
                      <img src={tpl.landingImage} alt={tpl.name} className="w-full h-full object-cover" />
                    </div>
                    <p className="mt-2 text-xs text-[color:var(--ink)]/70 text-center">{tpl.name}</p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Footer CTA */}
      <section className="py-24 md:py-32 px-6 md:px-12 bg-[color:var(--ink)] text-[color:var(--paper)]">
        <div className="max-w-[1400px] mx-auto flex flex-col md:flex-row items-end justify-between gap-8">
          <h2 className="font-serif-display text-5xl md:text-7xl leading-[0.95] max-w-2xl">
            {t("landing.footer.title_line1")}<br />{t("landing.footer.title_line2")}
          </h2>
          <button
            onClick={handleCreateAlbumClick}
            className="inline-flex items-center gap-3 bg-[color:var(--coral)] text-[color:var(--paper)] px-8 py-4 hover:bg-[color:var(--paper)] hover:text-[color:var(--ink)] transition-colors duration-300"
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
