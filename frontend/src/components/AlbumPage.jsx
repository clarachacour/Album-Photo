import React from "react";
import { photoImageUrl } from "@/lib/api";

/**
 * AlbumPage renders one printable page.
 * items: array of {type: "photo" | "text", photo_id, x, y, w, h, content, font, color, font_size}
 * Coordinates are normalized 0..1 (top-left origin).
 */
export function AlbumPage({ page, template, orientation = "portrait", pageIndex = 0, editable = false, onSelectItem, selectedItemId }) {
  const aspect = orientation === "landscape" ? "aspect-[1.414/1]" : "aspect-[1/1.414]";
  const items = page?.items || [];
  return (
    <div className={`relative w-full ${aspect} bg-[color:var(--paper)] overflow-hidden`}>
      <div className="absolute inset-0 grain pointer-events-none" />
      {items.map((item) => {
        const style = {
          left: `${item.x * 100}%`,
          top: `${item.y * 100}%`,
          width: `${item.w * 100}%`,
          height: `${item.h * 100}%`,
        };
        const isSel = selectedItemId === item.id;
        const ring = editable && isSel ? "outline outline-2 outline-[color:var(--coral)]" : "";
        if (item.type === "photo") {
          const scale = item.scale || 1;
          const focalX = item.focal_x ?? 0.5;
          const focalY = item.focal_y ?? 0.5;
          return (
            <div
              key={item.id}
              className={`absolute overflow-hidden ${ring}`}
              style={style}
              onClick={(e) => {
                if (!editable) return;
                e.stopPropagation();
                onSelectItem && onSelectItem(item);
              }}
              data-testid={`page-photo-${item.id}`}
            >
              <img
                src={photoImageUrl(item.photo_id)}
                alt=""
                className="w-full h-full object-cover"
                style={{
                  transform: `scale(${scale})`,
                  transformOrigin: `${focalX * 100}% ${focalY * 100}%`,
                  objectPosition: `${focalX * 100}% ${focalY * 100}%`,
                }}
                draggable={false}
              />
            </div>
          );
        }
        if (item.type === "text") {
          return (
            <div
              key={item.id}
              className={`absolute flex items-start ${ring}`}
              style={{
                ...style,
                color: item.color || "#1A1A17",
                fontFamily: item.font || "Cormorant Garamond, serif",
                fontSize: `${item.font_size || 16}px`,
                lineHeight: 1.15,
                overflow: "hidden",
                wordBreak: "break-word",
              }}
              onClick={(e) => {
                if (!editable) return;
                e.stopPropagation();
                onSelectItem && onSelectItem(item);
              }}
              data-testid={`page-text-${item.id}`}
            >
              <span className="whitespace-pre-wrap">{item.content}</span>
            </div>
          );
        }
        return null;
      })}
      {/* Page number */}
      <div className="absolute bottom-3 right-4 text-[10px] tracking-widest text-[color:var(--muted)] uppercase font-sans">
        {pageIndex + 1}
      </div>
    </div>
  );
}

/**
 * Cover Page (front) rendered as a "page" in the book flow.
 */
export function CoverFrontPage({ template, title, orientation, coverImageUrl }) {
  const aspect = orientation === "landscape" ? "aspect-[1.414/1]" : "aspect-[1/1.414]";
  const { bg, accent, text, illustration } = template;
  const SVGShape = getShape(illustration, accent);
  return (
    <div className={`relative w-full ${aspect} overflow-hidden flex flex-col justify-between p-6 md:p-10`} style={{ background: bg }}>
      <div className="absolute inset-0 grain pointer-events-none" />
      <h1
        className="font-serif-display leading-[0.95] tracking-tight relative z-10"
        style={{ color: text, fontSize: "clamp(28px, 6vw, 64px)", fontWeight: 600 }}
      >
        {title.split(" ").map((w, i) => (
          <span key={i} className="block uppercase">{w}</span>
        ))}
      </h1>
      {coverImageUrl ? (
        <div className="self-center w-[70%] aspect-[4/3] overflow-hidden">
          <img src={coverImageUrl} alt="Cover" className="w-full h-full object-cover" />
        </div>
      ) : (
        <div className="self-center">{SVGShape}</div>
      )}
      <div />
    </div>
  );
}

export function CoverBackPage({ template, country, year, orientation }) {
  const aspect = orientation === "landscape" ? "aspect-[1.414/1]" : "aspect-[1/1.414]";
  const { bg, text } = template;
  return (
    <div className={`relative w-full ${aspect} overflow-hidden flex flex-col items-center justify-between p-8`} style={{ background: bg }}>
      <div className="absolute inset-0 grain pointer-events-none" />
      <div />
      <div className="text-center">
        <div className="font-sans font-semibold tracking-[0.32em] uppercase" style={{ color: text, fontSize: "clamp(12px, 1.6vw, 18px)" }}>
          {country || ""}
        </div>
      </div>
      <div className="font-sans text-xs tracking-widest" style={{ color: text }}>
        {year || ""}
      </div>
    </div>
  );
}

function getShape(illustration, color) {
  const size = 200;
  switch (illustration) {
    case "coral":
      return (
        <svg viewBox="0 0 100 100" width={size} height={size}>
          <g fill={color}>
            <path d="M50 90 C 48 70 42 60 32 55 C 45 55 48 45 46 30 C 52 40 58 42 66 32 C 62 45 65 55 78 55 C 66 62 60 72 58 90 Z" />
            <circle cx="50" cy="20" r="4" />
            <circle cx="30" cy="35" r="3" />
            <circle cx="72" cy="42" r="3" />
          </g>
        </svg>
      );
    case "leaf":
      return (
        <svg viewBox="0 0 100 100" width={size} height={size}>
          <path d="M20 80 C 20 40 45 15 80 20 C 78 55 55 80 20 80 Z" fill={color} />
        </svg>
      );
    case "wave":
      return (
        <svg viewBox="0 0 100 100" width={size} height={size} fill="none" stroke={color} strokeWidth="4" strokeLinecap="round">
          <path d="M10 40 Q 30 20 50 40 T 90 40" />
          <path d="M10 55 Q 30 35 50 55 T 90 55" />
          <path d="M10 70 Q 30 50 50 70 T 90 70" />
        </svg>
      );
    case "sun":
      return (
        <svg viewBox="0 0 100 100" width={size} height={size}>
          <circle cx="50" cy="55" r="22" fill={color} />
          <g stroke={color} strokeWidth="3" strokeLinecap="round">
            <line x1="50" y1="15" x2="50" y2="25" />
            <line x1="50" y1="85" x2="50" y2="95" />
            <line x1="15" y1="55" x2="25" y2="55" />
            <line x1="75" y1="55" x2="85" y2="55" />
          </g>
        </svg>
      );
    case "mountain":
      return (
        <svg viewBox="0 0 100 100" width={size} height={size}>
          <path d="M5 80 L 30 40 L 50 65 L 70 30 L 95 80 Z" fill={color} />
        </svg>
      );
    case "bird":
      return (
        <svg viewBox="0 0 100 100" width={size} height={size}>
          <path d="M15 55 Q 30 30 50 45 Q 60 35 75 40 Q 85 50 80 65 Q 60 75 40 68 Q 22 65 15 55 Z" fill={color} />
        </svg>
      );
    default:
      return null;
  }
}
