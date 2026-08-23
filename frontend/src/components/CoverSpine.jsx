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

/** Tracks an element's live pixel width via ResizeObserver. */
function useElementWidth(ref) {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const el = ref.current;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) setWidth(entry.contentRect.width);
    });
    ro.observe(el);
    return () => ro.unobserve(el);
  }, [ref]);
  return width;
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
// The spine column's width is now proportional (see printDims.js) instead
// of a fixed 32px, so the safe max font size — the text's *thickness* in
// vertical-rl — is computed from the spine's actual measured width instead
// of a hardcoded constant. Above 1.0 lets letters use very slightly more
// than the raw column width (a small, deliberate bit of bleed most printed
// spines have anyway) — a shorter word (e.g. "Sicily") needs thicker
// letters than a longer one (e.g. "Barcelona") to cover a similar share of
// the spine's length, and 0.9 was clamping short words well below that,
// even with a generous box height, since height stops mattering entirely
// once a word's font size is capped by width.
const SPINE_MAX_FONT_RATIO = 1.05;
const SPINE_MAX_FONT_FALLBACK_PX = 29; // used only before the column's real width is known (first paint)
const SPINE_TITLE_SUBTITLE_GAP = 0.02; // small breathing room between the two, as a fraction of the spine's height

function useFitSpineFontSize({ containerHeight, maxFontPx, boxHeightFraction, title, baseFontSize, fontFamily, fontWeight, upright }) {
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
        const fitted = Math.min(REF_PX * (boxHeightPx / measured) * SAFETY, maxFontPx);
        setFontSize(Math.max(6, fitted));
        return;
      }

      const titleMeasured = measureDomTextWidth(String(title), {
        fontPx: REF_PX,
        fontWeight,
        fontFamily,
        letterSpacing: "-0.025em",
        uppercase: true,
      });
      const measured = Math.max(1, titleMeasured);
      const SAFETY = 0.86; // a bit more margin so the spine text never brushes the top/bottom edge
      let fitted = REF_PX * (boxHeightPx / measured) * SAFETY;
      // In vertical-rl, font-size is roughly the text's *thickness* —
      // without this cap, a short book with a tall-relative-to-width spine
      // (e.g. A5 landscape) computes a font size that fits the height fine
      // but is far too thick for the spine's actual width, overflowing it.
      fitted = Math.min(fitted, maxFontPx);
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
  }, [containerHeight, maxFontPx, boxHeightFraction, title, fontFamily, fontWeight, upright]);

  return fontSize;
}


/**
 * The book spine — shown between the back and front cover panels.
 * Title and year always mirror the real book title/year (a spine can't say
 * something different from the cover), but — like every other text on the
 * cover — they can be dragged to reposition, resized, and restyled (font,
 * size), or hidden entirely.
 */
export function CoverSpine({ title, year, template, cover = {}, editable = false, selectedZone, onSelectTitle, onSelectSubtitle, onSelectYear, onSelectCaption, onSelectLogo, onSelectDivider, onUpdateCover }) {
  const containerRef = useRef(null);
  const containerHeight = useElementHeight(containerRef);
  const containerWidth = useElementWidth(containerRef);
  const spineMaxFontPx = containerWidth ? containerWidth * SPINE_MAX_FONT_RATIO : SPINE_MAX_FONT_FALLBACK_PX;
  // Lets the person shrink spine text below its auto-fit size via the
  // right panel's Size slider — clamped so it can only ever go SMALLER
  // than the width-based cap, never bigger. Letting it exceed that cap
  // would reintroduce exactly the kind of cropping this whole exact-fit
  // system (see defaultTitleH/defaultSubtitleH below) was built to
  // eliminate — the cap isn't a stylistic choice, it's the actual physical
  // limit of how thick a letter can get before it doesn't fit the spine's
  // real width. Below 1, the slider is a genuine, real control on the
  // rendered size; the old spine_title_size/spine_subtitle_size/
  // spine_caption_size fields it used to write to had no lasting effect
  // once this auto-fit logic took over after the first render.
  const titleScale = Math.min(1, Math.max(0.4, cover.spine_title_scale ?? 1));
  const subtitleScale = Math.min(1, Math.max(0.4, cover.spine_subtitle_scale ?? 1));
  const captionScale = Math.min(1, Math.max(0.4, cover.spine_caption_scale ?? 1));
  const scaledTitleMaxFontPx = spineMaxFontPx * titleScale;
  const scaledSubtitleMaxFontPx = spineMaxFontPx * subtitleScale;
  const scaledCaptionMaxFontPx = spineMaxFontPx * captionScale;
  const bg = cover.bg_color || template.bg;
  const text = cover.text_color || template.text;
  const [titleEditing, setTitleEditing] = useState(false);
  const [subtitleEditing, setSubtitleEditing] = useState(false);
  const [captionEditing, setCaptionEditing] = useState(false);

  // Exact box-height computation, instead of a fixed or scaled fraction:
  // each box is sized to precisely match what its text needs to render at
  // its target font size — title targets the full width-based cap
  // (spineMaxFontPx); subtitle deliberately targets a fraction of it, so
  // it reads as clearly secondary rather than matching the title 1:1.
  // Sizing the box this way (inverting the same formula the fitting hook
  // below uses) is what actually eliminates both overlap (a box too small
  // for the size its text is entitled to render at) and dead gaps (a box
  // too big for it) at once — and it adapts automatically to word length
  // and to spine width, without a separately hand-tuned scale factor that
  // can drift out of sync with the real font-fitting math.
  const SUBTITLE_TO_TITLE_RATIO = 0.6; // subtitle renders at ~60% of the title's font size — "a little smaller", not tiny
  const SPINE_SAFETY = 0.86; // mirrors the SAFETY margin used inside useFitSpineFontSize
  const REF_PX = 100;
  const titleText = String(cover.spine_title_text || title || "Album");
  const subtitleText = String(cover.spine_subtitle || "");
  const titleFontSpec = {
    fontPx: REF_PX,
    fontWeight: cover.spine_title_weight || 700,
    fontFamily: cover.spine_title_font || "'Manrope', sans-serif",
    letterSpacing: "-0.025em",
    uppercase: true,
  };
  const subtitleFontSpec = {
    fontPx: REF_PX,
    fontWeight: cover.spine_subtitle_weight || 600,
    fontFamily: cover.spine_subtitle_font || cover.spine_title_font || "'Manrope', sans-serif",
    letterSpacing: "-0.025em",
    uppercase: true,
  };
  const titleMeasuredRef = containerWidth && containerHeight ? measureDomTextWidth(titleText, titleFontSpec) : 0;
  const subtitleMeasuredRef = containerWidth && containerHeight && subtitleText ? measureDomTextWidth(subtitleText, subtitleFontSpec) : 0;
  // The 0.75/0.55 ceilings here are only a last-resort safety net (e.g.
  // against a stray measurement glitch before layout has settled) — they
  // should essentially never be the thing determining a real word's box
  // size. They were previously much tighter (0.6/0.4) and that was
  // actively clipping legitimately long words (e.g. "Southeast Asia",
  // "Africa") instead of just guarding against edge cases.
  const defaultTitleH = titleMeasuredRef
    ? Math.min(0.75, (scaledTitleMaxFontPx * titleMeasuredRef / REF_PX / SPINE_SAFETY) / containerHeight)
    : 0.3;
  const defaultSubtitleH = subtitleMeasuredRef
    ? Math.min(0.55, (scaledSubtitleMaxFontPx * SUBTITLE_TO_TITLE_RATIO * subtitleMeasuredRef / REF_PX / SPINE_SAFETY) / containerHeight)
    : 0.18;

  const titleItem = {
    id: "spine-title",
    x: 0,
    // Pinned near the very top of the spine, with just a small margin so
    // it doesn't touch the edge — not centered.
    y: cover.spine_title_y ?? 0.05,
    w: 1,
    h: cover.spine_title_h ?? defaultTitleH,
  };
  const subtitleItem = {
    id: "spine-subtitle",
    x: 0,
    // A small gap after the title box — SPINE_TITLE_SUBTITLE_GAP is a
    // fraction of the spine's height, not tied to either box's own size,
    // so it stays a small, consistent breathing room regardless of word
    // length or spine width.
    y: cover.spine_subtitle_y ?? (titleItem.y + titleItem.h + SPINE_TITLE_SUBTITLE_GAP),
    w: 1,
    h: cover.spine_subtitle_h ?? defaultSubtitleH,
  };
  const yearItem = {
    id: "spine-year",
    x: 0,
    y: cover.spine_year_y ?? 0.82,
    w: 1,
    h: cover.spine_year_h ?? 0.14,
  };
  // The caption's underlying box (captionItem.h) is kept generously sized
  // — it only sets the *ceiling* the font-fitting effect below can grow
  // into, up to the width-based cap. The *visual* frame the person
  // actually sees (visualCaptionH, computed further down once the real
  // fitted font size is known) hugs the text tightly instead — deriving
  // the box size from a value computed independently, ahead of knowing
  // the actual fitted result, was consistently a bit off from what
  // actually rendered. This mirrors visualTitleH's approach for the front
  // cover title (see AlbumPage.jsx) — always derive the visible box from
  // the font size that was actually used, never a separate estimate of it.
  const captionMeasuredRef = containerWidth && containerHeight && cover.spine_caption
    ? measureDomTextWidth(String(cover.spine_caption), {
        fontPx: REF_PX,
        fontWeight: cover.spine_caption_weight || 600,
        fontFamily: cover.spine_caption_font || "'Manrope', sans-serif",
        letterSpacing: "normal",
        uppercase: false,
      })
    : 0;
  const captionItem = {
    id: "spine-caption",
    x: 0,
    y: cover.spine_caption_y ?? 0.82,
    w: 1,
    h: cover.spine_caption_h ?? 0.5,
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
      const maxPerLine = scaledCaptionMaxFontPx / Math.max(1, lines.length);
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
  }, [containerHeight, scaledCaptionMaxFontPx, captionItem.h, cover.spine_caption, cover.spine_caption_font, cover.spine_caption_weight, cover.spine_text_orientation]);
  const fittedSpineFontSizePx = useFitSpineFontSize({
    containerHeight,
    maxFontPx: scaledTitleMaxFontPx,
    boxHeightFraction: titleItem.h,
    title: cover.spine_title_text || title || "Album",
    baseFontSize: cover.spine_title_size || 9,
    fontFamily: cover.spine_title_font || "'Manrope', sans-serif",
    fontWeight: cover.spine_title_weight || "700",
    upright: cover.spine_text_orientation === "upright",
  });
  const spineTitleFontSizeStyle = containerHeight ? `${fittedSpineFontSizePx}px` : `${(((cover.spine_title_size || 9) / 608) * 100).toFixed(2)}cqh`;

  // A single-line caption (e.g. "MEMORIES") matches the title's font size
  // when that size also fits the caption's own text — two separate
  // calculations made same-styled words like "FAMILY" and "MEMORIES" land
  // on visibly different sizes for no real reason. But blindly reusing
  // the title's size broke down when the two words are very different
  // lengths (e.g. title "Dad" vs caption "MEMORIES") — a short title can
  // fit a much bigger font than a long caption word can, especially on a
  // wide (high page-count) spine, so the shared size overflowed the
  // caption's own space. Capped at the caption's own independent fit
  // (fittedCaptionFontSizePx, computed the same way as the title's) so it
  // only ever matches the title's size, never exceeds what the caption's
  // own text can actually fit. Multi-line captions (e.g. names + date)
  // keep their own fit outright, since they're a different shape of
  // content the title's size wouldn't suit anyway.
  const captionIsMultiLine = String(cover.spine_caption || "").includes("\n");
  const sharedCaptionFontPx = Math.min(fittedSpineFontSizePx, fittedCaptionFontSizePx);
  const spineCaptionFontSizeStyle = containerHeight
    ? `${captionIsMultiLine ? fittedCaptionFontSizePx : sharedCaptionFontPx}px`
    : `${(((cover.spine_caption_size || 9) / 608) * 100).toFixed(2)}cqh`;
  // Derived from whichever font size is *actually* rendered above (title's
  // size for a single-line caption, the caption's own fit for a
  // multi-line one) rather than a separate estimate computed ahead of
  // time — that estimate routinely diverged from the real result,
  // leaving a visible gap between a too-big box and the actual text.
  const actualCaptionFontPx = containerHeight
    ? (captionIsMultiLine ? fittedCaptionFontSizePx : sharedCaptionFontPx)
    : 0;
  const visualCaptionH =
    containerHeight && actualCaptionFontPx && captionMeasuredRef
      ? Math.min(captionItem.h, (actualCaptionFontPx * captionMeasuredRef / REF_PX / 0.9) / containerHeight)
      : captionItem.h;
  // The subtitle renders smaller than the title (0.72x, matching the ratio
  // the fit calculation above assumes) unless the template set its own
  // explicit spine_subtitle_size.
  const [fittedSubtitleFontSizePx, setFittedSubtitleFontSizePx] = useState(cover.spine_subtitle_size || 9);
  useLayoutEffect(() => {
    if (!containerHeight || !cover.spine_subtitle) return;
    const compute = () => {
      const boxHeightPx = subtitleItem.h * containerHeight;
      const REF_PX = 100;
      const upright = cover.spine_text_orientation === "upright";
      const measured = upright
        ? Math.max(1, String(cover.spine_subtitle).replace(/\s/g, "").length * REF_PX * 1.05)
        : measureDomTextWidth(String(cover.spine_subtitle), {
            fontPx: REF_PX,
            fontWeight: cover.spine_subtitle_weight || "600",
            fontFamily: cover.spine_subtitle_font || cover.spine_title_font || "'Manrope', sans-serif",
            letterSpacing: "-0.025em",
            // Must match the actual rendered casing (the subtitle is
            // forced uppercase via CSS) — measuring the un-uppercased text
            // undershoots real letter width and made the fitted font size
            // too big for what actually gets rendered, cropping it.
            uppercase: true,
          });
      setFittedSubtitleFontSizePx(Math.max(6, Math.min(REF_PX * (boxHeightPx / Math.max(1, measured)) * 0.86, scaledSubtitleMaxFontPx)));
    };
    compute();
    let cancelled = false;
    if (typeof document !== "undefined" && document.fonts && document.fonts.load) {
      const spec = `${cover.spine_subtitle_weight || 600} 16px ${cover.spine_subtitle_font || cover.spine_title_font || "'Manrope', sans-serif"}`;
      Promise.all([document.fonts.load(spec), document.fonts.ready]).then(() => {
        if (!cancelled) compute();
      }).catch(() => {});
    }
    return () => {
      cancelled = true;
    };
  }, [containerHeight, scaledSubtitleMaxFontPx, subtitleItem.h, cover.spine_subtitle, cover.spine_subtitle_font, cover.spine_subtitle_weight, cover.spine_title_font, cover.spine_text_orientation]);
  const spineSubtitleFontSizeStyle = containerHeight
    ? `${fittedSubtitleFontSizePx}px`
    : `${(((cover.spine_subtitle_size || 9) / 608) * 100).toFixed(2)}cqh`;

  return (
    <div ref={containerRef} className="relative h-full" style={{ background: bg, containerType: "size" }}>
      <div className="absolute inset-0 grain pointer-events-none" />
      {!cover.spine_title_hidden && (
        <DraggableItem
          item={titleItem}
          onChange={(patch) => onUpdateCover && onUpdateCover({ spine_title_y: patch.y ?? titleItem.y, spine_title_h: patch.h ?? titleItem.h })}
          onSelect={() => onSelectTitle && onSelectTitle()}
          onDoubleClick={() => setTitleEditing(true)}
          selected={selectedZone === "spine-title"}
          containerRef={containerRef}
          editable={editable && !titleEditing}
          tid="spine-title"
          minW={1}
        >
          {titleEditing ? (
            <textarea
              autoFocus
              value={cover.spine_title_text ?? title ?? ""}
              onChange={(e) => onUpdateCover && onUpdateCover({ spine_title_text: e.target.value })}
              onFocus={(e) => e.target.select()}
              onPointerDown={(e) => e.stopPropagation()}
              onBlur={() => setTitleEditing(false)}
              onKeyDown={(e) => {
                if (e.key === "Escape" || e.key === "Enter") { e.currentTarget.blur(); }
                e.stopPropagation();
              }}
              className="w-full h-full bg-transparent border-0 outline-none resize-none uppercase text-center"
              style={{
                color: cover.spine_title_color || text,
                writingMode: "vertical-rl",
                textOrientation: cover.spine_text_orientation === "upright" ? "upright" : "mixed",
                transform: undefined,
                fontSize: spineTitleFontSizeStyle,
                fontFamily: cover.spine_title_font || "'Manrope', sans-serif",
                fontWeight: cover.spine_title_weight || "700",
                lineHeight: 1,
              }}
              data-testid="spine-title-input"
            />
          ) : (
          <div
            className="w-full h-full flex items-center justify-center opacity-90 font-sans uppercase overflow-hidden pointer-events-none select-none whitespace-nowrap"
            style={{
              color: cover.spine_title_color || text,
              writingMode: "vertical-rl",
              textOrientation: cover.spine_text_orientation === "upright" ? "upright" : "mixed",
              transform: undefined,
              fontSize: spineTitleFontSizeStyle,
              fontFamily: cover.spine_title_font || "'Manrope', sans-serif",
              fontWeight: cover.spine_title_weight || "700",
              lineHeight: 1,
            }}
          >
            <span>{String(cover.spine_title_text || title || "Album").toUpperCase()}</span>
          </div>
          )}
        </DraggableItem>
      )}
      {cover.spine_subtitle && (
        <DraggableItem
          item={subtitleItem}
          onChange={(patch) => onUpdateCover && onUpdateCover({ spine_subtitle_y: patch.y ?? subtitleItem.y, spine_subtitle_h: patch.h ?? subtitleItem.h })}
          onSelect={() => onSelectSubtitle && onSelectSubtitle()}
          onDoubleClick={() => setSubtitleEditing(true)}
          selected={selectedZone === "spine-subtitle"}
          containerRef={containerRef}
          editable={editable && !subtitleEditing}
          tid="spine-subtitle"
          minW={1}
        >
          {subtitleEditing ? (
            <textarea
              autoFocus
              value={cover.spine_subtitle || ""}
              onChange={(e) => onUpdateCover && onUpdateCover({ spine_subtitle: e.target.value })}
              onFocus={(e) => e.target.select()}
              onPointerDown={(e) => e.stopPropagation()}
              onBlur={() => setSubtitleEditing(false)}
              onKeyDown={(e) => {
                if (e.key === "Escape" || e.key === "Enter") { e.currentTarget.blur(); }
                e.stopPropagation();
              }}
              className="w-full h-full bg-transparent border-0 outline-none resize-none text-center uppercase"
              style={{
                color: cover.spine_subtitle_color || text,
                writingMode: "vertical-rl",
                textOrientation: cover.spine_text_orientation === "upright" ? "upright" : "mixed",
                transform: undefined,
                fontSize: spineSubtitleFontSizeStyle,
                fontFamily: cover.spine_subtitle_font || cover.spine_title_font || "'Manrope', sans-serif",
                fontWeight: cover.spine_subtitle_weight || "600",
                lineHeight: 1,
              }}
              data-testid="spine-subtitle-input"
            />
          ) : (
            <div
              className="w-full h-full flex items-center justify-center font-sans uppercase overflow-hidden pointer-events-none select-none whitespace-nowrap"
              style={{
                color: cover.spine_subtitle_color || text,
                writingMode: "vertical-rl",
                textOrientation: cover.spine_text_orientation === "upright" ? "upright" : "mixed",
                transform: undefined,
                fontSize: spineSubtitleFontSizeStyle,
                fontFamily: cover.spine_subtitle_font || cover.spine_title_font || "'Manrope', sans-serif",
                fontWeight: cover.spine_subtitle_weight || "600",
                lineHeight: 1,
              }}
            >
              {cover.spine_subtitle}
            </div>
          )}
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
              color: cover.spine_year_color || text,
              writingMode: "vertical-rl",
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
              // Matches the text's own rendered thickness (the title's
              // fitted font size) rather than spanning the full spine
              // width — the divider should read as part of the text's own
              // width, not a full-width rule.
              width: containerHeight ? `${fittedSpineFontSizePx}px` : "60%",
              height: "1.6px",
              background: cover.spine_caption_color || text,
              transform: "translate(-50%, -50%)",
            }}
          />
        </DraggableItem>
      )}
      {cover.spine_caption && (
        <DraggableItem
          item={{ ...captionItem, h: visualCaptionH }}
          onChange={(patch) => onUpdateCover && onUpdateCover({ spine_caption_y: patch.y ?? captionItem.y, spine_caption_h: patch.h ?? captionItem.h })}
          onSelect={() => onSelectCaption && onSelectCaption()}
          onDoubleClick={() => setCaptionEditing(true)}
          selected={selectedZone === "spine-caption"}
          containerRef={containerRef}
          editable={editable && !captionEditing}
          tid="spine-caption"
          minW={1}
        >
          {captionEditing ? (
            <textarea
              autoFocus
              value={cover.spine_caption || ""}
              onChange={(e) => onUpdateCover && onUpdateCover({ spine_caption: e.target.value })}
              onFocus={(e) => e.target.select()}
              onPointerDown={(e) => e.stopPropagation()}
              onBlur={() => setCaptionEditing(false)}
              onKeyDown={(e) => {
                if (e.key === "Escape") { e.currentTarget.blur(); }
                e.stopPropagation();
              }}
              className="w-full h-full bg-transparent border-0 outline-none resize-none text-center"
              style={{
                color: cover.spine_caption_color || text,
                writingMode: "vertical-rl",
                textOrientation: cover.spine_text_orientation === "upright" ? "upright" : "mixed",
                transform: undefined,
                fontSize: spineCaptionFontSizeStyle,
                fontFamily: cover.spine_caption_font || "'Manrope', sans-serif",
                fontWeight: cover.spine_caption_weight || "600",
                lineHeight: 1,
              }}
              data-testid="spine-caption-input"
            />
          ) : (
          <div
            className="w-full h-full flex items-center justify-center font-sans overflow-hidden pointer-events-none select-none"
            style={{
              color: cover.spine_caption_color || text,
              writingMode: "vertical-rl",
              textOrientation: cover.spine_text_orientation === "upright" ? "upright" : "mixed",
              transform: undefined,
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
          )}
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
