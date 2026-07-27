import React, { useState, useRef, useEffect } from "react";
import { Rnd } from "react-rnd";
import { DEFAULT_COVER, DEFAULT_TITLE_FONT } from "@/lib/coverTemplates";

export function CoverMockup({
  cover,
  title = "Your title",
  year = new Date().getFullYear(),
  country = "Country",
  showLabels = false,
  selectedItemId,
  onSelectItem,
  onUpdateItem,
  onUpdateTitlePos,
}) {
  const c = { ...DEFAULT_COVER, ...(cover || {}) };
  const { bg_color: bg, accent_color: accent, text_color: text } = c;
  const imageSrc = c.image_url || c.image;

  const extraItems = c.extra_items || [];
  const frontCoverRef = useRef(null);

  // Dimensions réelles du conteneur
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });

  // Lignes de centrage dynamiques (X et Y)
  const [snapLines, setSnapLines] = useState({ x: null, y: null });

  // Utilisation de ResizeObserver pour capturer la vraie taille du conteneur dès le montage
  useEffect(() => {
    if (!frontCoverRef.current) return;

    const observeTarget = frontCoverRef.current;
    const resizeObserver = new ResizeObserver((entries) => {
      for (let entry of entries) {
        if (entry.contentRect) {
          setContainerSize({
            width: entry.contentRect.width,
            height: entry.contentRect.height,
          });
        }
      }
    });

    resizeObserver.observe(observeTarget);
    return () => resizeObserver.unobserve(observeTarget);
  }, []);

  // Détection du centrage (Snap Guides)
  const checkSnapGuides = (x, y, width, height) => {
    if (!containerSize.width || !containerSize.height) return;

    const centerX = containerSize.width / 2;
    const centerY = containerSize.height / 2;

    const itemCenterX = x + width / 2;
    const itemCenterY = y + height / 2;

    const THRESHOLD = 8; // Marge d'alignement en px

    const isNearX = Math.abs(itemCenterX - centerX) < THRESHOLD;
    const isNearY = Math.abs(itemCenterY - centerY) < THRESHOLD;

    setSnapLines({
      x: isNearX ? centerX : null,
      y: isNearY ? centerY : null,
    });
  };

  // Calcul des dimensions absolues en pixels
  const titleX = (c.title_x ?? 0.05) * containerSize.width;
  const titleY = (c.title_y ?? 0.05) * containerSize.height;
  const titleW = (c.title_w ?? 0.9) * containerSize.width;
  const titleH = (c.title_h ?? 0.2) * containerSize.height;

  return (
    <div className="w-full">
      <div className="grid grid-cols-[1fr_28px_1fr] gap-0 rounded-sm overflow-hidden book-shadow">
        {/* Back cover */}
        <div
          className="relative aspect-[3/4] flex items-center justify-center"
          style={{ background: bg }}
        >
          <div className="absolute inset-0 grain pointer-events-none" />
          <div
            className="text-[9px] md:text-[10px] tracking-[0.3em] uppercase font-sans font-semibold opacity-90 text-center px-2"
            style={{ color: text }}
          >
            {country}
          </div>
        </div>

        {/* Spine */}
        <div
          className="relative flex flex-col items-center justify-between py-3"
          style={{ background: bg }}
        >
          <div
            className="opacity-80 text-[7px] tracking-[0.3em] font-sans font-semibold uppercase"
            style={{
              color: text,
              writingMode: "vertical-rl",
              transform: "rotate(180deg)",
            }}
          >
            {title}
          </div>
          <div
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: accent }}
          />
          <div
            className="text-[7px] font-sans font-semibold tracking-widest"
            style={{
              color: text,
              writingMode: "vertical-rl",
              transform: "rotate(180deg)",
            }}
          >
            {year}
          </div>
        </div>

        {/* Front cover */}
        <div
          ref={frontCoverRef}
          className="relative aspect-[3/4] flex flex-col justify-between overflow-hidden"
          style={{ background: bg }}
          onClick={() => {
            if (onSelectItem) onSelectItem(null);
          }}
        >
          {/* Ligne Guide Verticale (Axe X) */}
          {snapLines.x !== null && (
            <div
              className="absolute top-0 bottom-0 border-l-2 border-dashed border-[color:var(--coral,#f53769)] z-50 pointer-events-none"
              style={{ left: `${snapLines.x}px` }}
            />
          )}

          {/* Ligne Guide Horizontale (Axe Y) */}
          {snapLines.y !== null && (
            <div
              className="absolute left-0 right-0 border-t-2 border-dashed border-[color:var(--coral,#f53769)] z-50 pointer-events-none"
              style={{ top: `${snapLines.y}px` }}
            />
          )}

          {/* Image de fond ou Grain */}
          {imageSrc ? (
            <img
              src={imageSrc}
              alt={title}
              className="absolute inset-0 w-full h-full object-cover pointer-events-none select-none"
            />
          ) : (
            <div className="absolute inset-0 grain pointer-events-none" />
          )}

          {imageSrc && (
            <div className="absolute inset-0 bg-black/10 pointer-events-none" />
          )}

          {/* 1. TITRE PRINCIPAL DÉPLAÇABLE AVEC RND */}
          {containerSize.width > 0 && (
            <Rnd
              size={{ width: titleW, height: titleH }}
              position={{ x: titleX, y: titleY }}
              bounds="parent"
              onDrag={(e, d) => checkSnapGuides(d.x, d.y, titleW, titleH)}
              onDragStop={(e, d) => {
                setSnapLines({ x: null, y: null });
                if (onUpdateTitlePos && containerSize.width && containerSize.height) {
                  onUpdateTitlePos({
                    title_x: d.x / containerSize.width,
                    title_y: d.y / containerSize.height,
                  });
                }
              }}
              onResizeStop={(e, dir, ref, delta, pos) => {
                setSnapLines({ x: null, y: null });
                if (onUpdateTitlePos && containerSize.width && containerSize.height) {
                  onUpdateTitlePos({
                    title_w: parseFloat(ref.style.width) / containerSize.width,
                    title_h: parseFloat(ref.style.height) / containerSize.height,
                    title_x: pos.x / containerSize.width,
                    title_y: pos.y / containerSize.height,
                  });
                }
              }}
              onMouseDown={(e) => {
                e.stopPropagation();
                if (onSelectItem) onSelectItem("title");
              }}
              className={`absolute z-30 cursor-move border transition-colors ${
                selectedItemId === "title"
                  ? "border-2 border-[color:var(--coral,#f53769)]"
                  : "border-transparent hover:border-black/20"
              }`}
            >
              <h3
                className="w-full h-full leading-[0.95] tracking-tight select-none flex flex-col justify-start pointer-events-none"
                style={{
                  color: text,
                  fontSize: "clamp(14px, 3.4vw, 26px)",
                  fontWeight: c.title_font_weight || 800,
                  fontFamily: c.title_font || DEFAULT_TITLE_FONT,
                }}
              >
                {(title || "Album").split(" ").map((w, i) => (
                  <span key={i} className="block uppercase">
                    {w}
                  </span>
                ))}
              </h3>
            </Rnd>
          )}

          {/* 2. ÉLÉMENTS SUPPLÉMENTAIRES (EXTRA ITEMS) */}
          {containerSize.width > 0 &&
            extraItems.map((it) => {
              const isSelected = selectedItemId === it.id;
              const itemX = (it.x ?? 0.1) * containerSize.width;
              const itemY = (it.y ?? 0.1) * containerSize.height;
              const itemW = (it.w ?? 0.3) * containerSize.width;
              const itemH = (it.h ?? 0.3) * containerSize.height;

              return (
                <Rnd
                  key={it.id}
                  size={{ width: itemW, height: itemH }}
                  position={{ x: itemX, y: itemY }}
                  bounds="parent"
                  onDrag={(e, d) => checkSnapGuides(d.x, d.y, itemW, itemH)}
                  onDragStop={(e, d) => {
                    setSnapLines({ x: null, y: null });
                    if (onUpdateItem && containerSize.width && containerSize.height) {
                      onUpdateItem(it.id, {
                        x: d.x / containerSize.width,
                        y: d.y / containerSize.height,
                      });
                    }
                  }}
                  onResizeStop={(e, dir, ref, delta, pos) => {
                    setSnapLines({ x: null, y: null });
                    if (onUpdateItem && containerSize.width && containerSize.height) {
                      onUpdateItem(it.id, {
                        w: parseFloat(ref.style.width) / containerSize.width,
                        h: parseFloat(ref.style.height) / containerSize.height,
                        x: pos.x / containerSize.width,
                        y: pos.y / containerSize.height,
                      });
                    }
                  }}
                  onMouseDown={(e) => {
                    e.stopPropagation();
                    if (onSelectItem) onSelectItem(it.id);
                  }}
                  className={`absolute z-20 cursor-move border transition-colors ${
                    isSelected
                      ? "border-2 border-[color:var(--coral,#f53769)]"
                      : "border-transparent hover:border-black/20"
                  }`}
                >
                  {it.type === "image" || it.image_url ? (
                    <img
                      src={it.image_url}
                      alt=""
                      className="w-full h-full object-contain pointer-events-none select-none"
                    />
                  ) : (
                    <div
                      className="w-full h-full select-none pointer-events-none"
                      style={{
                        color: it.color || text,
                        fontSize: `${it.fontSize || 14}px`,
                        fontFamily: it.fontFamily || "sans-serif",
                      }}
                    >
                      {it.text || "Texte"}
                    </div>
                  )}
                </Rnd>
              );
            })}

          {/* Badge central par défaut si aucune image */}
          {!imageSrc && !extraItems.some((it) => it.type === "image") && (
            <div className="relative z-10 self-center pointer-events-none my-auto">
              <div
                className="rounded-full"
                style={{ width: 90, height: 90, background: accent }}
              />
            </div>
          )}
        </div>
      </div>

      {showLabels && (
        <div className="mt-3 text-center text-[10px] tracking-widest uppercase text-[color:var(--muted,#888)]">
          Cover Preview
        </div>
      )}
    </div>
  );
}

export function CoverFront({ cover, title = "Album" }) {
  const c = { ...DEFAULT_COVER, ...(cover || {}) };
  const { bg_color: bg, accent_color: accent, text_color: text } = c;
  const imageSrc = c.image_url || c.image;
  const extras = c.extra_items || [];
  const hasImageExtra = extras.some((it) => it.type === "image");
  const titleX = c.title_x ?? 0.08;
  const titleY = c.title_y ?? 0.08;
  const titleW = c.title_w ?? 0.84;

  // The book editor renders a full page at ~500px wide, and title_font_size
  // is stored as an absolute px value calibrated against that width. Using
  // "cqw" (container query width) instead of "vw" scales the title relative
  // to *this card's own width*, so a small dashboard thumbnail still shows
  // text at the same proportion as the real, full-size cover.
  const REFERENCE_PAGE_PX = 500;
  const titleFontSizePx = c.title_font_size || 48;
  const titleFontSizeCqw = (titleFontSizePx / REFERENCE_PAGE_PX) * 100;

  return (
    <div
      className="relative aspect-[3/4] w-full overflow-hidden book-shadow rounded-sm"
      style={{ background: bg, containerType: "inline-size" }}
    >
      {imageSrc ? (
        <img
          src={imageSrc}
          alt={title}
          className="absolute inset-0 w-full h-full object-cover"
        />
      ) : (
        <div className="absolute inset-0 grain pointer-events-none" />
      )}
      {imageSrc && <div className="absolute inset-0 bg-black/10" />}

      {!imageSrc &&
        extras.map((item) => {
          if (item.type === "image") {
            return (
              <img
                key={item.id}
                src={item.image_url}
                alt=""
                className="absolute object-contain pointer-events-none select-none"
                style={{
                  left: `${item.x * 100}%`,
                  top: `${item.y * 100}%`,
                  width: `${item.w * 100}%`,
                  height: `${item.h * 100}%`,
                }}
              />
            );
          }
          if (item.type === "shape") {
            return (
              <div
                key={item.id}
                className="absolute pointer-events-none"
                style={{
                  left: `${item.x * 100}%`,
                  top: `${item.y * 100}%`,
                  width: `${item.w * 100}%`,
                  height: `${item.h * 100}%`,
                  background: item.fill_color || accent,
                  borderRadius: item.shape_type === "circle" ? "9999px" : 0,
                }}
              />
            );
          }
          if (item.type === "text") {
            return (
              <div
                key={item.id}
                className="absolute pointer-events-none whitespace-pre-wrap"
                style={{
                  left: `${item.x * 100}%`,
                  top: `${item.y * 100}%`,
                  width: `${item.w * 100}%`,
                  height: `${item.h * 100}%`,
                  color: item.color || text,
                  fontFamily: item.font || "'Manrope', sans-serif",
                  fontSize: `${((item.font_size || 16) / REFERENCE_PAGE_PX) * 100}cqw`,
                  fontWeight: item.font_weight || "normal",
                  overflow: "hidden",
                }}
              >
                {item.content}
              </div>
            );
          }
          return null;
        })}

      {!imageSrc && !hasImageExtra && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div
            className="rounded-full"
            style={{ width: 60, height: 60, background: accent }}
          />
        </div>
      )}

      <h3
        className="absolute leading-[0.95] tracking-tight uppercase"
        style={{
          left: `${titleX * 100}%`,
          top: `${titleY * 100}%`,
          width: `${titleW * 100}%`,
          color: text,
          fontSize: `clamp(6px, ${titleFontSizeCqw}cqw, 300px)`,
          fontWeight: c.title_font_weight || 800,
          fontFamily: c.title_font || DEFAULT_TITLE_FONT,
        }}
      >
        {title}
      </h3>
    </div>
  );
}