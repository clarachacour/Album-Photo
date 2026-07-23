import React from "react";

// Simple SVG illustrations by name for cover previews
function Illustration({ name, color, size = 200 }) {
  const s = size;
  const stroke = color;
  const fill = color;
  switch (name) {
    case "coral":
      return (
        <svg viewBox="0 0 100 100" width={s} height={s} aria-hidden>
          <g fill={fill}>
            <path d="M50 90 C 48 70 42 60 32 55 C 45 55 48 45 46 30 C 52 40 58 42 66 32 C 62 45 65 55 78 55 C 66 62 60 72 58 90 Z" />
            <circle cx="50" cy="20" r="4" />
            <circle cx="30" cy="35" r="3" />
            <circle cx="72" cy="42" r="3" />
          </g>
        </svg>
      );
    case "leaf":
      return (
        <svg viewBox="0 0 100 100" width={s} height={s} aria-hidden>
          <g fill={fill}>
            <path d="M20 80 C 20 40 45 15 80 20 C 78 55 55 80 20 80 Z" />
            <path d="M25 75 L 75 25" stroke={stroke === fill ? "#fff" : stroke} strokeWidth="1.5" opacity="0.6" />
          </g>
        </svg>
      );
    case "wave":
      return (
        <svg viewBox="0 0 100 100" width={s} height={s} aria-hidden>
          <g fill="none" stroke={stroke} strokeWidth="4" strokeLinecap="round">
            <path d="M10 40 Q 30 20 50 40 T 90 40" />
            <path d="M10 55 Q 30 35 50 55 T 90 55" />
            <path d="M10 70 Q 30 50 50 70 T 90 70" />
          </g>
        </svg>
      );
    case "sun":
      return (
        <svg viewBox="0 0 100 100" width={s} height={s} aria-hidden>
          <g fill={fill}>
            <circle cx="50" cy="55" r="22" />
            <g stroke={stroke} strokeWidth="3" strokeLinecap="round">
              <line x1="50" y1="15" x2="50" y2="25" />
              <line x1="50" y1="85" x2="50" y2="95" />
              <line x1="15" y1="55" x2="25" y2="55" />
              <line x1="75" y1="55" x2="85" y2="55" />
              <line x1="25" y1="30" x2="32" y2="37" />
              <line x1="68" y1="73" x2="75" y2="80" />
              <line x1="25" y1="80" x2="32" y2="73" />
              <line x1="68" y1="37" x2="75" y2="30" />
            </g>
          </g>
        </svg>
      );
    case "mountain":
      return (
        <svg viewBox="0 0 100 100" width={s} height={s} aria-hidden>
          <g fill={fill}>
            <path d="M5 80 L 30 40 L 50 65 L 70 30 L 95 80 Z" />
            <path d="M25 45 L 30 40 L 35 45 L 32 48 L 28 48 Z" fill="#fff" opacity="0.4" />
            <path d="M65 35 L 70 30 L 75 35 L 72 38 L 68 38 Z" fill="#fff" opacity="0.4" />
          </g>
        </svg>
      );
    case "bird":
      return (
        <svg viewBox="0 0 100 100" width={s} height={s} aria-hidden>
          <g fill={fill}>
            <path d="M15 55 Q 30 30 50 45 Q 60 35 75 40 Q 85 50 80 65 Q 60 75 40 68 Q 22 65 15 55 Z" />
            <circle cx="70" cy="48" r="2" fill={stroke === fill ? "#000" : stroke} />
          </g>
        </svg>
      );
    default:
      return null;
  }
}

// Full cover mockup: back + spine + front laid out horizontally
export function CoverMockup({ template, title = "Western Australia", year = 2026, country = "AUSTRALIA", showLabels = false }) {
  const { bg, accent, text, illustration } = template;
  return (
    <div className="w-full">
      <div className="grid grid-cols-[1fr_28px_1fr] gap-0 rounded-sm overflow-hidden book-shadow">
        {/* Back cover */}
        <div
          className="relative aspect-[3/4] flex items-center justify-center"
          style={{ background: bg }}
        >
          <div className="absolute inset-0 grain pointer-events-none" />
          <div className="opacity-90" style={{ color: text }}>
            <svg viewBox="0 0 120 100" width={80} height={70} aria-hidden>
              <path d="M20 45 Q 25 30 45 32 Q 55 25 70 30 Q 90 28 95 45 Q 100 55 88 65 Q 78 78 60 75 Q 40 78 28 68 Q 15 60 20 45 Z"
                    fill="none" stroke={text} strokeWidth="2" />
            </svg>
          </div>
        </div>
        {/* Spine */}
        <div
          className="relative flex flex-col items-center justify-between py-3"
          style={{ background: bg }}
        >
          <div className="opacity-80 text-[7px] tracking-[0.3em] font-sans font-semibold uppercase"
               style={{ color: text, writingMode: "vertical-rl", transform: "rotate(180deg)" }}>
            {title}
          </div>
          <div
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: accent }}
          />
          <div className="text-[7px] font-sans font-semibold tracking-widest"
               style={{ color: text, writingMode: "vertical-rl", transform: "rotate(180deg)" }}>
            {year}
          </div>
        </div>
        {/* Front cover */}
        <div
          className="relative aspect-[3/4] flex flex-col justify-between p-3 md:p-4"
          style={{ background: bg }}
        >
          <div className="absolute inset-0 grain pointer-events-none" />
          <h3
            className="font-serif-display leading-[0.95] tracking-tight"
            style={{ color: text, fontSize: "clamp(14px, 3.4vw, 26px)", fontWeight: 600 }}
          >
            {title.split(" ").map((w, i) => (
              <span key={i} className="block uppercase">{w}</span>
            ))}
          </h3>
          <div className="self-center">
            <Illustration name={illustration} color={accent} size={90} />
          </div>
          <div />
        </div>
      </div>
      {showLabels && (
        <div className="grid grid-cols-[1fr_28px_1fr] mt-3 text-[10px] tracking-widest uppercase text-[color:var(--muted)]">
          <span className="text-center">Couverture arrière</span>
          <span />
          <span className="text-center">Couverture avant</span>
        </div>
      )}
    </div>
  );
}

// A single front-only cover for smaller previews / dashboards
export function CoverFront({ template, title = "Album", small = false }) {
  const { bg, accent, text, illustration } = template;
  return (
    <div
      className="relative aspect-[3/4] w-full overflow-hidden book-shadow flex flex-col justify-between p-4"
      style={{ background: bg }}
    >
      <div className="absolute inset-0 grain pointer-events-none" />
      <h3
        className="font-serif-display leading-[0.95] tracking-tight"
        style={{ color: text, fontSize: small ? "clamp(10px, 2.2vw, 16px)" : "clamp(14px, 3vw, 22px)", fontWeight: 600 }}
      >
        {title.split(" ").slice(0, 4).map((w, i) => (
          <span key={i} className="block uppercase">{w}</span>
        ))}
      </h3>
      <div className="self-center">
        <Illustration name={illustration} color={accent} size={small ? 60 : 100} />
      </div>
      <div />
    </div>
  );
}
