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
// The spine column is a fixed 32px wide in the cover layout grid
// (grid-cols-[1fr_32px_1fr]) regardless of page format/orientation — no
// spine font size should ever be allowed to exceed a safe thickness for
// that fixed column, no matter what a height-only fill calculation says.
const SPINE_MAX_FONT_PX = 29;

function useFitSpineFontSize({ containerHeight, boxHeightFraction, title, subtitle, baseFontSize, fontFamily, fontWeight, upright }) {
  const [fontSize, setFontSize] = useState(baseFontSize || 9);

  useLayoutEffect(() => {
    if (!containerHeight || !title) return;

    const compute = () => {
      const boxHeightPx = boxHeightFraction * containerHeight;
      const REF_PX = 100;

      if (upright) {
        // Upright letters (text-orientation: upright) stack top to bottom
        // each roughly its own font-size tall, rather than flowing as one
        // continuous sideways run — character count is what determines the
        // length here, not a horizontal width measurement.
        const chars = String(title).replace(/\s/g, "").length;
        const measured = Math.max(1, chars * REF_PX * 1.05);
        const SAFETY = 0.86;
        const fitted = Math.min(REF_PX * (boxHeightPx / measured) * SAFETY, SPINE_MAX_FONT_PX);
        setFontSize(Math.max(6, fitted));
        return;
      }

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
      let fitted = REF_PX * (boxHeightPx / measured) * SAFETY;
      // The spine column itself is a fixed 32px wide (see the grid-cols-
      // [1fr_32px_1fr] layout) no matter the page format/orientation. In
      // vertical-rl, font-size is roughly the text's *thickness* — without
      // this cap, a short book with a tall-relative-to-width spine (e.g. A5
      // landscape) computes a font size that fits the height fine but is
      // far too thick for that fixed width, overflowing the column.
      fitted = Math.min(fitted, SPINE_MAX_FONT_PX);
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
  }, [containerHeight, boxHeightFraction, title, subtitle, fontFamily, fontWeight, upright]);

  return fontSize;
}


/**
 * The book spine — shown between the back and front cover panels.
 * Title and year always mirror the real book title/year (a spine can't say
 * something different from the cover), but — like every other text on the
 * cover — they can be dragged to reposition, resized, and restyled (font,
 * size), or hidden entirely.
 */
export function CoverSpine({ title, year, template, cover = {}, editable = false, selectedZone, onSelectTitle, onSelectYear, onSelectCaption, onSelectLogo, onSelectDivider, onUpdateCover }) {
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
  const captionItem = {
    id: "spine-caption",
    x: 0,
    y: cover.spine_caption_y ?? 0.82,
    w: 1,
    h: cover.spine_caption_h ?? 0.16,
  };
  const dividerItem = {
    id: "spine-divider",
    x: 0,
    // Defaults to sitting right at the caption's own top edge — no gap
    // before the caption text starts — rather than centered in whatever
    // space happens to exist between the title and caption boxes.
    y: cover.spine_divider_y ?? captionItem.y - 0.02,
    w: 1,
    h: cover.spine_divider_h ?? 0.022,
  };
  const logoItem = {
    id: "spine-logo",
    x: cover.spine_logo_x ?? 0.28,
    y: cover.spine_logo_y ?? 0.86,
    w: cover.spine_logo_w ?? 0.44,
    h: cover.spine_logo_h ?? 0.08,
  };

  // The caption can be any 2 lines the person types (e.g. names + date), so
  // rather than trust the stored size to always fit, measure the longer of
  // the two lines and fit it to the box's real height — same idea as the
  // title fit above, just per-line instead of one continuous run.
  const [fittedCaptionFontSizePx, setFittedCaptionFontSizePx] = useState(cover.spine_caption_size || 9);
  useLayoutEffect(() => {
    if (!containerHeight || !cover.spine_caption) return;
    const compute = () => {
      const boxHeightPx = captionItem.h * containerHeight;
      const REF_PX = 100;
      const lines = String(cover.spine_caption).split("\n");
      const upright = cover.spine_text_orientation === "upright";
      const widest = upright
        ? Math.max(1, ...lines.map((line) => line.replace(/\s/g, "").length * REF_PX * 1.05))
        : Math.max(
            1,
            ...lines.map((line) =>
              measureDomTextWidth(line, {
                fontPx: REF_PX,
                fontWeight: cover.spine_caption_weight || "600",
                fontFamily: cover.spine_caption_font || "'Manrope', sans-serif",
                letterSpacing: "normal",
                uppercase: false,
              })
            )
          );
      // Each stacked line shares the same fixed-width column, so the safe
      // per-line thickness shrinks as more lines are stacked (2 lines means
      // each can only be about half as thick as a single line could be).
      const maxPerLine = SPINE_MAX_FONT_PX / Math.max(1, lines.length);
      setFittedCaptionFontSizePx(Math.max(6, Math.min(REF_PX * (boxHeightPx / widest) * 0.9, maxPerLine)));
    };
    compute();
    let cancelled = false;
    if (typeof document !== "undefined" && document.fonts && document.fonts.load) {
      const spec = `${cover.spine_caption_weight || 600} 16px ${cover.spine_caption_font || "'Manrope', sans-serif"}`;
      Promise.all([document.fonts.load(spec), document.fonts.ready]).then(() => {
        if (!cancelled) compute();
      }).catch(() => {});
    }
    return () => {
      cancelled = true;
    };
  }, [containerHeight, captionItem.h, cover.spine_caption, cover.spine_caption_font, cover.spine_caption_weight, cover.spine_text_orientation]);
  const fittedSpineFontSizePx = useFitSpineFontSize({
    containerHeight,
    boxHeightFraction: titleItem.h,
    title: cover.spine_title_text || title || "Album",
    subtitle: cover.spine_subtitle,
    baseFontSize: cover.spine_title_size || 9,
    fontFamily: cover.spine_title_font || "'Manrope', sans-serif",
    fontWeight: cover.spine_title_weight || "700",
    upright: cover.spine_text_orientation === "upright",
  });
  const spineTitleFontSizeStyle = containerHeight ? `${fittedSpineFontSizePx}px` : `${(((cover.spine_title_size || 9) / 608) * 100).toFixed(2)}cqh`;

  // A single-line caption (e.g. "MEMORIES") matches the title's font size
  // directly instead of using its own independent word-length-based fit —
  // two separate calculations made same-styled words like "FAMILY" and
  // "MEMORIES" land on visibly different sizes for no real reason. Multi-
  // line captions (e.g. names + date) keep their own fit, since they're a
  // different shape of content the title's size wouldn't suit.
  const captionIsMultiLine = String(cover.spine_caption || "").includes("\n");
  const spineCaptionFontSizeStyle = containerHeight
    ? `${captionIsMultiLine ? fittedCaptionFontSizePx : fittedSpineFontSizePx}px`
    : `${(((cover.spine_caption_size || 9) / 608) * 100).toFixed(2)}cqh`;
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
            className="w-full h-full flex items-center justify-center opacity-90 font-sans uppercase overflow-hidden pointer-events-none select-none whitespace-nowrap"
            style={{
              color: cover.spine_title_color || text,
              writingMode: "vertical-rl",
              textOrientation: cover.spine_text_orientation === "upright" ? "upright" : "mixed",
              transform: cover.spine_text_orientation === "upright" ? undefined : "rotate(180deg)",
              fontSize: spineTitleFontSizeStyle,
              fontFamily: cover.spine_title_font || "'Manrope', sans-serif",
              fontWeight: cover.spine_title_weight || "700",
              lineHeight: 1,
            }}
          >
            <span>{String(cover.spine_title_text || title || "Album").toUpperCase()}</span>
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
              lineHeight: 1,
            }}
          >
            {year || ""}
          </div>
        </DraggableItem>
      )}
      {cover.spine_title_caption_divider && (
        <DraggableItem
          item={dividerItem}
          onChange={(patch) => onUpdateCover && onUpdateCover({ spine_divider_y: patch.y ?? dividerItem.y, spine_divider_h: patch.h ?? dividerItem.h })}
          onSelect={() => onSelectDivider && onSelectDivider()}
          selected={selectedZone === "spine-divider"}
          containerRef={containerRef}
          editable={editable}
          tid="spine-divider"
          minW={1}
          minH={0.02}
        >
          <div
            className="absolute left-1/2 top-1/2 pointer-events-none"
            style={{
              width: "1.6px",
              height: "140%",
              background: cover.spine_caption_color || text,
              transform: "translate(-50%, -50%) rotate(45deg)",
            }}
          />
        </DraggableItem>
      )}
      {cover.spine_caption && (
        <DraggableItem
          item={captionItem}
          onChange={(patch) => onUpdateCover && onUpdateCover({ spine_caption_y: patch.y ?? captionItem.y, spine_caption_h: patch.h ?? captionItem.h })}
          onSelect={() => onSelectCaption && onSelectCaption()}
          selected={selectedZone === "spine-caption"}
          containerRef={containerRef}
          editable={editable}
          tid="spine-caption"
          minW={1}
        >
          <div
            className="w-full h-full flex items-center justify-center font-sans overflow-hidden pointer-events-none select-none"
            style={{
              color: cover.spine_caption_color || text,
              writingMode: "vertical-rl",
              textOrientation: cover.spine_text_orientation === "upright" ? "upright" : "mixed",
              transform: cover.spine_text_orientation === "upright" ? undefined : "rotate(180deg)",
              whiteSpace: "pre",
              fontSize: spineCaptionFontSizeStyle,
              fontFamily: cover.spine_caption_font || "'Manrope', sans-serif",
              fontWeight: cover.spine_caption_weight || "600",
              lineHeight: 1,
              textAlign: "center",
            }}
          >
            {cover.spine_caption}
          </div>
        </DraggableItem>
      )}
      {cover.spine_logo_image && (
        <DraggableItem
          item={logoItem}
          onChange={(patch) => onUpdateCover && onUpdateCover({ spine_logo_x: patch.x ?? logoItem.x, spine_logo_y: patch.y ?? logoItem.y, spine_logo_w: patch.w ?? logoItem.w, spine_logo_h: patch.h ?? logoItem.h })}
          onSelect={() => onSelectLogo && onSelectLogo()}
          selected={selectedZone === "spine-logo"}
          containerRef={containerRef}
          editable={editable}
          tid="spine-logo"
          minW={0.1}
          minH={0.02}
        >
          {cover.spine_logo_lines && (
            <div
              className="absolute left-1/2 pointer-events-none"
              style={{ top: "4%", height: "2px", width: "90%", background: cover.spine_caption_color || text, transform: "translateX(-50%)" }}
            />
          )}
          <img
            src={cover.spine_logo_image}
            alt=""
            className="w-full h-full object-contain pointer-events-none select-none"
            style={{ transform: cover.spine_logo_rotation ? `rotate(${cover.spine_logo_rotation}deg)` : undefined }}
            draggable={false}
          />
          {cover.spine_logo_lines && (
            <div
              className="absolute left-1/2 pointer-events-none"
              style={{ bottom: "4%", height: "2px", width: "90%", background: cover.spine_caption_color || text, transform: "translateX(-50%)" }}
            />
          )}
        </DraggableItem>
      )}
    </div>
  );
}