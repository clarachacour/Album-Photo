import React from "react";
import { useNavigate } from "react-router-dom";
import { COVER_THEMES } from "@/lib/coverThemes";
import { ArrowLeft, ArrowRight } from "lucide-react";

export default function ChooseTemplate() {
  const nav = useNavigate();

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-24 pb-24 px-6 md:px-12">
      <div className="max-w-[1400px] mx-auto">
        <button
          onClick={() => nav("/dashboard")}
          className="eyebrow inline-flex items-center gap-2 mb-8 text-[color:var(--muted)] hover:text-[color:var(--ink)] transition-colors"
        >
          <ArrowLeft size={14} /> Back
        </button>

        <h1 className="font-serif-display text-4xl md:text-6xl tracking-tight mb-4">Choose a starting look.</h1>
        <p className="text-[color:var(--ink)]/70 mb-12 max-w-xl">
          Every detail — colors, title, photos, layout — stays fully editable afterward. Or start from a blank canvas if you'd rather build your own.
        </p>

        <button
          onClick={() => nav("/create")}
          data-testid="template-blank"
          className="w-full flex items-center justify-between border border-[color:var(--ink)]/20 hover:border-[color:var(--ink)] transition-colors p-6 mb-14"
        >
          <div className="text-left">
            <div className="font-serif-display text-xl mb-1">Start from scratch</div>
            <div className="text-sm text-[color:var(--ink)]/60">The classic blank template — pick your own colors and layout.</div>
          </div>
          <ArrowRight size={18} />
        </button>

        {COVER_THEMES.map((theme) => (
          <div key={theme.id} className="mb-16">
            <h2 className="font-serif-display text-2xl mb-5">{theme.label}</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-4">
              {theme.templates.map((tpl) => (
                <button
                  key={tpl.id}
                  onClick={() => nav(`/create?template=${tpl.id}`)}
                  data-testid={`template-option-${tpl.id}`}
                  className="text-left group"
                >
                  <div className="aspect-[3/4] overflow-hidden book-shadow rounded-sm group-hover:opacity-90 transition-opacity">
                    <img src={tpl.landingImage} alt={tpl.name} className="w-full h-full object-cover" />
                  </div>
                  <p className="mt-2 text-xs text-[color:var(--ink)]/70 group-hover:text-[color:var(--ink)]">{tpl.name}</p>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}