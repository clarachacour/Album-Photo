import React from "react";
import { DEFAULT_COVER, DEFAULT_TITLE_FONT } from "@/lib/coverTemplates";

// Full cover mockup: back cover + spine (title + year) + front cover.
// Every visual element (bg/accent/text color, custom image, title, country, year)
// is driven by the `cover` object and the album's own title/country/year — fully editable.
export function CoverMockup({ cover, title = "Your title", year = new Date().getFullYear(), country = "Country", showLabels = false }) {
  const c = { ...DEFAULT_COVER, ...(cover || {}) };
  const { bg_color: bg, accent_color: accent, text_color: text } = c;
  const imageSrc = c.image_url || c.image;

  return (
    <div className="w-full">
      <div className="grid grid-cols-[1fr_28px_1fr] gap-0 rounded-sm overflow-hidden book-shadow">
        {/* Back cover */}
        <div className="relative aspect-[3/4] flex items-center justify-center" style={{ background: bg }}>
          <div className="absolute inset-0 grain pointer-events-none" />
          <div
            className="text-[9px] md:text-[10px] tracking-[0.3em] uppercase font-sans font-semibold opacity-90 text-center px-2"
            style={{ color: text }}
          >
            {country}
          </div>
        </div>
        {/* Spine */}
        <div className="relative flex flex-col items-center justify-between py-3" style={{ background: bg }}>
          <div
            className="opacity-80 text-[7px] tracking-[0.3em] font-sans font-semibold uppercase"
            style={{ color: text, writingMode: "vertical-rl", transform: "rotate(180deg)" }}
          >
            {title}
          </div>
          <div className="w-1.5 h-1.5 rounded-full" style={{ background: accent }} />
          <div
            className="text-[7px] font-sans font-semibold tracking-widest"
            style={{ color: text, writingMode: "vertical-rl", transform: "rotate(180deg)" }}
          >
            {year}
          </div>
        </div>
        {/* Front cover */}
        <div className="relative aspect-[3/4] flex flex-col justify-between p-3 md:p-4 overflow-hidden" style={{ background: bg }}>
          {imageSrc ? (
            <img src={imageSrc} alt={title} className="absolute inset-0 w-full h-full object-cover" />
          ) : (
            <div className="absolute inset-0 grain pointer-events-none" />
          )}
          {/* Subtle scrim so the title stays readable over a custom image */}
          {imageSrc && <div className="absolute inset-0 bg-black/10" />}
          <h3
            className="relative z-10 leading-[0.95] tracking-tight"
            style={{
              color: text,
              fontSize: "clamp(14px, 3.4vw, 26px)",
              fontWeight: c.title_font_weight || 800,
              fontFamily: c.title_font || DEFAULT_TITLE_FONT,
            }}
          >
            {(title || "Album").split(" ").map((w, i) => (
              <span key={i} className="block uppercase">{w}</span>
            ))}
          </h3>
          {!imageSrc && (c.extra_items || []).filter((it) => it.type === "image").map((it) => (
            <img
              key={it.id}
              src={it.image_url}
              alt=""
              className="absolute object-contain pointer-events-none select-none"
              style={{ left: `${it.x * 100}%`, top: `${it.y * 100}%`, width: `${it.w * 100}%`, height: `${it.h * 100}%` }}
            />
          ))}
          {!imageSrc && !(c.extra_items || []).some((it) => it.type === "image") && (
            <div className="relative z-10 self-center">
              <div className="rounded-full" style={{ width: 90, height: 90, background: accent }} />
            </div>
          )}
        </div>
      </div>
      {showLabels && (
        <div className="mt-3 text-center text-[10px] tracking-widest uppercase text-[color:var(--muted)]">
          Cover Preview
        </div>
      )}
    </div>
  );
}

// Front-only cover for compact previews (dashboard cards, etc.)
export function CoverFront({ cover, title = "Album" }) {
  const c = { ...DEFAULT_COVER, ...(cover || {}) };
  const { bg_color: bg, accent_color: accent, text_color: text } = c;
  const imageSrc = c.image_url || c.image;
  const logoItem = !imageSrc && (c.extra_items || []).find((it) => it.type === "image");

  return (
    <div className="relative aspect-[3/4] w-full overflow-hidden book-shadow rounded-sm" style={{ background: bg }}>
      {imageSrc ? (
        <img src={imageSrc} alt={title} className="absolute inset-0 w-full h-full object-cover" />
      ) : (
        <div className="absolute inset-0 grain pointer-events-none" />
      )}
      {imageSrc && <div className="absolute inset-0 bg-black/10" />}
      {logoItem && (
        <img
          src={logoItem.image_url}
          alt=""
          className="absolute object-contain pointer-events-none select-none"
          style={{ left: `${logoItem.x * 100}%`, top: `${logoItem.y * 100}%`, width: `${logoItem.w * 100}%`, height: `${logoItem.h * 100}%` }}
        />
      )}
      {!imageSrc && !logoItem && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="rounded-full" style={{ width: 60, height: 60, background: accent }} />
        </div>
      )}
      <div className="relative z-10 p-3 h-full flex items-end">
        <h3
          className="leading-[0.95] tracking-tight uppercase"
          style={{ color: text, fontSize: "clamp(12px, 2.6vw, 18px)", fontWeight: c.title_font_weight || 800, fontFamily: c.title_font || DEFAULT_TITLE_FONT }}
        >
          {title}
        </h3>
      </div>
    </div>
  );
}