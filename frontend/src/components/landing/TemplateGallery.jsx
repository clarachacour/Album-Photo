import React from "react";
import { useTranslation } from "react-i18next";
import { COVER_THEMES } from "@/lib/coverThemes";

/** The cover templates shown on the landing page, grouped by theme. */
export default function TemplateGallery() {
  const { t } = useTranslation();
  return COVER_THEMES.map((theme) => (
    <div key={theme.id} className="mb-14">
      <h3 className="font-serif-display text-2xl mb-5">{t(`landing.templates.themes.${theme.id}`, { defaultValue: theme.label })}</h3>
      <div className="flex gap-4 overflow-x-auto pb-2">
        {theme.templates.map((tpl) => (
          <div key={tpl.id} className="shrink-0 w-40 md:w-48">
            <div className="aspect-[3/4] overflow-hidden book-shadow rounded-sm">
              <img src={tpl.landingImage} alt={tpl.name} width={480} height={640} loading="lazy" decoding="async" className="w-full h-full object-cover" />
            </div>
            <p className="mt-2 text-xs text-[color:var(--ink)]/70 text-center">{tpl.name}</p>
          </div>
        ))}
      </div>
    </div>
  ));
}
