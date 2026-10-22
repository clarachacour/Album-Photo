import React from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { COVER_THEMES } from "@/lib/coverThemes";

/** The cover templates shown on the landing page, grouped by theme. Each
 * one starts an album with it (signing in first if needed). */
export default function TemplateGallery() {
  const { t } = useTranslation();
  return COVER_THEMES.map((theme) => (
    <div key={theme.id} className="mb-14">
      <h3 className="font-serif-display text-2xl mb-5">{t(`landing.templates.themes.${theme.id}`, { defaultValue: theme.label })}</h3>
      <div className="flex gap-4 overflow-x-auto pb-2">
        {theme.templates.map((tpl) => (
          <Link
            key={tpl.id}
            to={`/create?template=${tpl.id}`}
            className="group shrink-0 w-40 md:w-48"
            data-testid={`landing-template-${tpl.id}`}
          >
            <div className="relative aspect-[3/4] overflow-hidden book-shadow rounded-sm">
              <img src={tpl.landingImage} alt="" width={480} height={640} loading="lazy" decoding="async" className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-[1.03]" />
              <span className="absolute inset-x-0 bottom-0 bg-[color:var(--ink)] text-[color:var(--paper)] text-[11px] font-semibold tracking-widest uppercase text-center py-2 opacity-0 group-hover:opacity-90 group-focus-visible:opacity-90 [@media(hover:none)]:opacity-90 transition-opacity">
                {t("landing.templates.useThis")}
              </span>
            </div>
            <p className="mt-2 text-xs text-ink/70 text-center group-hover:text-[color:var(--ink)]">{tpl.name}</p>
          </Link>
        ))}
      </div>
    </div>
  ));
}
