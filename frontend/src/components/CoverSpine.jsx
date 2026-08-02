import React, { useRef, useState, useLayoutEffect, useEffect } from "react";
import { DraggableItem, measureDomTextWidth } from "@/components/AlbumPage";

/** Tracks an element's live pixel height via ResizeObserver. */
function useElementHeight(ref) {
  const [height, setHeight] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const el = ref.current;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) setHeight(entry.contentRect.height);
    });
    ro.observe(el);
    return () => ro.unobserve(el);
  }, [ref]);
  return height;
}

/**
 * Fits the (rotated) spine title+subtitle to the full height of their box,
 * the same way the front cover title fills its box's width — otherwise the
 * spine text ends up looking small and disconnected from the front cover's
 * now-full-width title, since it used a fixed, un-scaled font size before.
 * Uses the same real-DOM measurement as the front title (see AlbumPage.jsx)
 * so the tight letter-spacing it now shares with the front title is
 * reflected automatically, instead of hand-adjusted per property.
 */
function useFitSpineFontSize({ containerHeight, boxHeightFraction, title, subtitle, baseFontSize, fontFamily, fontWeight }) {
  const [fontSize, setFontSize] = useState(baseFontSize || 9);

  useLayoutEffect(() => {
    if (!containerHeight || !title) return;

    const compute = () => {
      const boxHeightPx = boxHeightFraction * containerHeight;
      const REF_PX = 100;
      // Rotated 90°, so the text's rendered *width* becomes its vertical
      // extent — title, a thin space, then subtitle, back to back. The
      // subtitle renders at a smaller ratio than the title, not the same
      // size (matches the front cover, where the subtitle is smaller too).
      const SUBTITLE_RATIO = 0.72;
      const titleMeasured = measureDomTextWidth(String(title), {
        fontPx: REF_PX,
        fontWeight,
        fontFamily,
        letterSpacing: "-0.025em",
        uppercase: true,
      });
      const subtitleMeasured = subtitle
        ? measureDomTextWidth(` ${subtitle}`, {
            fontPx: REF_PX * SUBTITLE_RATIO,
            fontWeight,
            fontFamily,
            letterSpacing: "-0.025em",
            uppercase: true,
          })
        : 0;
      const measured = Math.max(1, titleMeasured + subtitleMeasured);
      const SAFETY = 0.86; // a bit more margin so the spine text never brushes the top/bottom edge
      const fitted = REF_PX * (boxHeightPx / measured) * SAFETY;
      setFontSize(Math.max(6, fitted));
    };

    compute();
    let cancelled = false;
    if (typeof document !== "undefined" && document.fonts && document.fonts.load) {
      const spec = `${fontWeight || 700} 16px ${fontFamily}`;
      Promise.all([document.fonts.load(spec), document.fonts.ready])
        .then(() => {
          if (!cancelled) compute();
        })
        .catch(() => {});
    }
    return () => {
      cancelled = true;
    };
  }, [containerHeight, boxHeightFraction, title, subtitle, fontFamily, fontWeight]);

  return fontSize;
}


/**
 * The book spine — shown between the back and front cover panels.
 * Title and year always mirror the real book title/year (a spine can't say
 * something different from the cover), but — like every other text on the
 * cover — they can be dragged to reposition, resized, and restyled (font,
 * size), or hidden entirely.
 */
export function CoverSpine({ title, year, template, cover = {}, editable = false, selectedZone, onSelectTitle, onSelectYear, onUpdateCover }) {
  const containerRef = useRef(null);
  const containerHeight = useElementHeight(containerRef);
  const bg = cover.bg_color || template.bg;
  const text = cover.text_color || template.text;

  const titleItem = {
    id: "spine-title",
    x: 0,
    y: cover.spine_title_y ?? 0.08,
    w: 1,
    h: cover.spine_title_h ?? 0.8,
  };
  const yearItem = {
    id: "spine-year",
    x: 0,
    y: cover.spine_year_y ?? 0.82,
    w: 1,
    h: cover.spine_year_h ?? 0.14,
  };

  const fittedSpineFontSizePx = useFitSpineFontSize({
    containerHeight,
    boxHeightFraction: titleItem.h,
    title: title || "Album",
    subtitle: cover.spine_subtitle,
    baseFontSize: cover.spine_title_size || 9,
    fontFamily: cover.spine_title_font || "'Manrope', sans-serif",
    fontWeight: cover.spine_title_weight || "700",
  });
  const spineTitleFontSizeStyle = containerHeight ? `${fittedSpineFontSizePx}px` : `${(((cover.spine_title_size || 9) / 608) * 100).toFixed(2)}cqh`;
  // The subtitle renders smaller than the title (0.72x, matching the ratio
  // the fit calculation above assumes) unless the template set its own
  // explicit spine_subtitle_size.
  const SPINE_SUBTITLE_RATIO = 0.72;
  const spineSubtitleFontSizeStyle = cover.spine_subtitle_size
    ? (containerHeight ? `${fittedSpineFontSizePx * (cover.spine_subtitle_size / (cover.spine_title_size || 9))}px` : `${(((cover.spine_subtitle_size) / 608) * 100).toFixed(2)}cqh`)
    : (containerHeight ? `${fittedSpineFontSizePx * SPINE_SUBTITLE_RATIO}px` : spineTitleFontSizeStyle);

  return (
    <div ref={containerRef} className="relative h-full" style={{ background: bg, containerType: "size" }}>
      <div className="absolute inset-0 grain pointer-events-none" />
      {!cover.spine_title_hidden && (
        <DraggableItem
          item={titleItem}
          onChange={(patch) => onUpdateCover && onUpdateCover({ spine_title_y: patch.y ?? titleItem.y, spine_title_h: patch.h ?? titleItem.h })}
          onSelect={() => onSelectTitle && onSelectTitle()}
          selected={selectedZone === "spine-title"}
          containerRef={containerRef}
          editable={editable}
          tid="spine-title"
          minW={1}
        >
          <div
            className="w-full h-full flex items-center justify-center opacity-90 tracking-tight font-sans uppercase overflow-hidden pointer-events-none select-none whitespace-nowrap"
            style={{
              color: text,
              writingMode: "vertical-rl",
              transform: "rotate(180deg)",
              fontSize: spineTitleFontSizeStyle,
              fontFamily: cover.spine_title_font || "'Manrope', sans-serif",
              fontWeight: cover.spine_title_weight || "700",
            }}
          >
            <span>{title || "Album"}</span>
            {cover.spine_subtitle && (
              <span
                className=""
                style={{
                  color: cover.spine_subtitle_color || text,
                  fontSize: spineSubtitleFontSizeStyle,
                  fontFamily: cover.spine_subtitle_font || cover.spine_title_font || "'Manrope', sans-serif",
                  fontWeight: cover.spine_subtitle_weight || "600",
                }}
              >
                {"\u00A0" + cover.spine_subtitle}
              </span>
            )}
          </div>
        </DraggableItem>
      )}
      {!cover.spine_year_hidden && (
        <DraggableItem
          item={yearItem}
          onChange={(patch) => onUpdateCover && onUpdateCover({ spine_year_y: patch.y ?? yearItem.y, spine_year_h: patch.h ?? yearItem.h })}
          onSelect={() => onSelectYear && onSelectYear()}
          selected={selectedZone === "spine-year"}
          containerRef={containerRef}
          editable={editable}
          tid="spine-year"
          minW={1}
        >
          <div
            className="w-full h-full flex items-center justify-center font-sans tracking-widest overflow-hidden pointer-events-none select-none"
            style={{
              color: text,
              writingMode: "vertical-rl",
              transform: "rotate(180deg)",
              fontSize: `${(((cover.spine_year_size || 9) / 608) * 100).toFixed(2)}cqh`,
              fontFamily: cover.spine_year_font || "'Manrope', sans-serif",
              fontWeight: cover.spine_year_weight || "700",
            }}
          >
            {year || ""}
          </div>
        </DraggableItem>
      )}
    </div>
  );
}