import React from "react";
import { Link } from "react-router-dom";
import { COVER_TEMPLATES } from "@/lib/coverTemplates";
import { CoverMockup } from "@/components/CoverPreview";
import { TID } from "@/constants/testIds";
import { ArrowRight, Sparkles, BookOpen, Wand2 } from "lucide-react";

export default function Landing() {
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
              A photo book
              <br />
              <span className="italic text-[color:var(--coral)]">signed</span> by your memories.
            </h1>
            <p className="mt-8 text-lg md:text-xl text-[color:var(--ink)]/70 max-w-xl leading-relaxed font-sans">
              Upload your photos, and we'll turn them into a refined printed album, crafted to feel timeless and made to be kept
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-4">
              <Link
                to="/auth"
                data-testid={TID.landingCta}
                className="group inline-flex items-center gap-3 bg-[color:var(--ink)] text-[color:var(--paper)] px-8 py-4 hover:bg-[color:var(--coral)] transition-colors duration-300"
              >
                <span className="text-sm font-semibold tracking-widest uppercase">Create my album</span>
                <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
              </Link>
              <a href="#templates" data-testid={TID.landingSecondaryCta} className="text-sm font-semibold tracking-widest uppercase text-[color:var(--ink)]/60 hover:text-[color:var(--ink)] px-2 py-2 border-b border-[color:var(--ink)]/40 transition-colors">
                View covers
              </a>
            </div>
          </div>

          <div className="md:col-span-5 animate-fade-up" style={{ animationDelay: "0.15s" }}>
            <div className="max-w-md mx-auto md:ml-auto">
              <CoverMockup
                template={COVER_TEMPLATES[0]}
                title="Western Australia"
                year={2026}
                country="Australia"
                showLabels
              />
            </div>
          </div>
        </div>
      </section>

      {/* Process strip */}
      <section className="border-y border-[color:var(--border-soft)] py-16 md:py-24 bg-white">
        <div className="max-w-[1400px] mx-auto px-6 md:px-12 grid grid-cols-1 md:grid-cols-3 gap-12">
          {[
            {
              icon: <Wand2 size={22} />,
              title: "You upload",
              body: "All your photos, unorganized — duplicates, blurry shots, HDR. We accept everything.",
              n: "01",
            },
            {
              icon: <Sparkles size={22} />,
              title: "AI sorts",
              body: "Gemini analyzes each shot: composition, duplicates, and grouping by scene.",
              n: "02",
            },
            {
              icon: <BookOpen size={22} />,
              title: "You flip",
              body: "A 3D flipbook, varied layouts, and a high-resolution PDF export.",
              n: "03",
            },
          ].map((s, i) => (
            <div key={i} className="flex gap-6 items-start">
              <div className="font-serif-display text-4xl text-[color:var(--coral)]">{s.n}</div>
              <div>
                <div className="flex items-center gap-2 text-[color:var(--ink)] mb-2">
                  {s.icon}
                  <h3 className="font-serif-display text-2xl">{s.title}</h3>
                </div>
                <p className="text-[color:var(--ink)]/70 leading-relaxed">{s.body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Templates gallery */}
      <section id="templates" className="py-24 md:py-32 px-6 md:px-12">
        <div className="max-w-[1400px] mx-auto">
          <div className="mb-16 md:mb-24 max-w-2xl">
            <div className="eyebrow mb-4">Library</div>
            <h2 className="font-serif-display text-4xl md:text-6xl tracking-tight leading-[1]">
              Six covers.<br />
              <em className="not-italic text-[color:var(--muted)]">Endless stories.</em>
            </h2>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-16">
            {COVER_TEMPLATES.map((tpl, i) => (
              <div key={tpl.id} className="animate-fade-up" style={{ animationDelay: `${i * 0.06}s` }}>
                <CoverMockup
                  template={tpl}
                  title={sampleTitle(tpl.id)}
                  year={2026}
                  country={sampleCountry(tpl.id)}
                />
                <div className="mt-4">
                  <div className="eyebrow text-[color:var(--ink)]/60">{tpl.name}</div>
                  <div className="text-sm font-sans text-[color:var(--ink)]/70 mt-1">{tpl.mood}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer CTA */}
      <section className="py-24 md:py-32 px-6 md:px-12 bg-[color:var(--ink)] text-[color:var(--paper)]">
        <div className="max-w-[1400px] mx-auto flex flex-col md:flex-row items-end justify-between gap-8">
          <h2 className="font-serif-display text-5xl md:text-7xl leading-[0.95] max-w-2xl">
            Ready to design<br />your edition?
          </h2>
          <Link
            to="/auth"
            className="inline-flex items-center gap-3 bg-[color:var(--coral)] text-[color:var(--paper)] px-8 py-4 hover:bg-[color:var(--paper)] hover:text-[color:var(--ink)] transition-colors duration-300"
            data-testid="footer-cta"
          >
            <span className="text-sm font-semibold tracking-widest uppercase">Create my photo album</span>
            <ArrowRight size={16} />
          </Link>
        </div>
      </section>
    </main>
  );
}

function sampleTitle(id) {
  return {
    "teal-coral": "Western Australia",
    "sand-forest": "Marrakech",
    "navy-blush": "Tokyo Neon",
    "terracotta-cream": "Sahara South",
    "forest-gold": "Nordic Trails",
    "charcoal-rose": "Paris Nocturne",
  }[id] || "Album";
}
function sampleCountry(id) {
  return {
    "teal-coral": "Australia",
    "sand-forest": "Morocco",
    "navy-blush": "Japan",
    "terracotta-cream": "Algeria",
    "forest-gold": "Norway",
    "charcoal-rose": "France",
  }[id] || "";
}