import React, { useRef, useState, useEffect } from "react";
import { PhotoFrameToolbar, PhotoEditToolbar, PhotoPanOverlay } from "@/components/ItemToolbars";
import { ImagePlus } from "lucide-react";
import { AutoFitText } from "@/components/book/AutoFitText";
import { CenterGuides } from "@/components/book/CenterGuides";
import { DraggableItem } from "@/components/book/DraggableItem";
import { REFERENCE_PAGE_PX, measureDomTextWidth } from "@/components/book/textMeasure";
import { useElementWidth } from "@/components/book/useElementWidth";
import { useFitTitleFontSize } from "@/components/book/useFitTitleFontSize";
import { DEFAULT_TITLE_BOX } from "@/lib/coverDefaults";
import { findTemplate } from "@/lib/coverThemes";
import { FramedPhoto } from "@/components/book/FramedPhoto";
import { minZoom, pageAspect as pageAspectWH } from "@/lib/photoFit";

/**
 * Cover front page — now fully editable: background/accent/text colors overridable,
 * title position movable, optional custom cover image, and extra_items support
 * (text pieces that can be added and moved on the cover).
 */
export function CoverFrontPage({
  template,
  title,
  orientation,
  coverImageUrl,
  cover = {},
  templateId,
  editable = false,
  onSelectItem,
  onUpdateItem,
  onSelectTitle,
  onUpdateTitle,
  onTitleTextChange,
  onSelectCover,
  selectedItemId,
  titleSelected,
}) {
  const containerRef = useRef(null);
  const containerWidth = useElementWidth(containerRef);
  const [titleEditing, setTitleEditing] = useState(false);
  const [extraTextEditId, setExtraTextEditId] = useState(null);
  // Which cover photo (if any) is currently in pan/zoom/rotate mode. Purely
  // local UI state — not persisted, same idea as the interior page editor's
  // cropMode.
  const [cropItemId, setCropItemId] = useState(null);
  const aspect = orientation === "landscape" ? "aspect-[1.414/1]" : "aspect-[1/1.414]";
  const bg = cover.bg_color || template.bg;
  const accent = cover.accent_color || template.accent;
  const text = cover.text_color || template.text;
  const titleFont = cover.title_font || "'Baloo 2', sans-serif";
  const titleWeight = cover.title_font_weight || "800";
  const titleX = cover.title_x ?? DEFAULT_TITLE_BOX.x;
  const titleY = cover.title_y ?? DEFAULT_TITLE_BOX.y;
  const titleW = cover.title_w ?? DEFAULT_TITLE_BOX.w;
  const titleH = cover.title_h ?? DEFAULT_TITLE_BOX.h;
  const titleFontSize = cover.title_font_size || null;
  const titleRotation = cover.title_rotation || 0;
  const titleWritingMode = cover.title_writing_mode || null; // "vertical-rl" keeps the box's own footprint, unlike rotate() which pivots around the box's center
  const titleUppercase = cover.title_uppercase !== false;
  const titleFontStyle = cover.title_font_style || "normal";
  const titleSingleLine = !!cover.title_single_line;
  const titleTextAlign = cover.title_text_align || "left";
  const extras = cover.extra_items || [];
  const [draggingId, setDraggingId] = useState(null);
  const [loadedAspects, setLoadedAspects] = useState({});
  // Bumped exactly once, after actively triggering every font this cover
  // needs (title + all subtitle-role extras) to load. Confirmed by
  // inspecting the real rendered PDF export: a subtitle's font-size came
  // out at 17.04cqw in a box only 50% wide — nowhere near enough room for
  // that text at that size — meaning the overflow-cap measurement (see
  // renderItem below) had run against a narrower fallback font before the
  // real one had loaded, letting an oversized value through uncapped.
  // document.fonts.ready ALONE doesn't fix this: it only tracks fonts
  // already in the process of loading, and does nothing to trigger
  // loading a font that's only referenced in CSS but hasn't been used by
  // any painted/measured text yet — which is exactly the situation the
  // very first measurement of a subtitle is in. document.fonts.load()
  // actively requests the font instead of passively waiting, then
  // document.fonts.ready confirms it (and everything else) has actually
  // finished. Runs once per mount ([] deps, not re-derived from extras on
  // every render) specifically to avoid the repeated-firing risk
  // suspected in an earlier, per-render version of this same fix.
  const [fontsSettled, setFontsSettled] = useState(false);
  useEffect(() => {
    if (typeof document === "undefined" || !document.fonts || !document.fonts.load) return;
    let cancelled = false;
    const specs = new Set([`${titleWeight} 16px ${titleFont}`]);
    for (const it of extras) {
      if (it.type === "text") specs.add(`${it.font_weight || "normal"} 16px ${it.font || titleFont}`);
    }
    Promise.all([...specs].map((spec) => document.fonts.load(spec)))
      .catch(() => {})
      .then(() => document.fonts.ready)
      .catch(() => {})
      .then(() => {
        if (!cancelled) setFontsSettled(true);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // height = width * pageAspect. Was hardcoded to the portrait ratio
  // (1.414) everywhere, which silently broke every size/position
  // calculation below in landscape orientation (text and images
  // overlapping) since the assumed page shape didn't match the real one.
  const pageAspect = orientation === "landscape" ? 1 / 1.414 : 1.414;

  // Fills the full width of the title box for every template — shrinks long
  // words so they never bleed past the cover edge, and grows short words so
  // they aren't left looking small in an oversized box. Capped by the box's
  // own height so a short word in a multi-line title doesn't blow up past
  // what the box can actually hold.
  const fittedTitleFontSizePx = useFitTitleFontSize({
    containerWidth,
    boxWidthFraction: titleW,
    boxHeightFraction: titleH,
    lineCount: (titleWritingMode || titleSingleLine) ? 1 : String(title || "").split(" ").length,
    text: title,
    storedFontSize: titleFontSize,
    fontFamily: titleFont,
    fontWeight: titleWeight,
    uppercase: titleUppercase,
    writingMode: titleWritingMode,
    pageAspect,
    singleLine: titleSingleLine,
    scale: cover.title_scale ?? 1,
    // Albums made before this setting existed don't carry it: read it from
    // their template.
    fitHeight: cover.title_fit_height ?? !!findTemplate(templateId)?.cover?.title_fit_height,
  });
  const titleFontSizeStyle = containerWidth ? `${fittedTitleFontSizePx}px` : "clamp(18px, 9cqw, 56px)";

  // The stored title_h was sized for the old fixed font_size and is often
  // taller than the text actually needs now that the font fills the box's
  // width dynamically. Shrink the *visual* box to hug the fitted text so
  // the selection frame matches the title instead of leaving empty space
  // below it (the subtitle, positioned right at the box's bottom edge,
  // then sits right under the real text too). Manual resizing by the user
  // still writes to title_h as before via onUpdateTitle.
  const titleLineCount = (titleWritingMode || titleSingleLine) ? 1 : String(title || "").split(" ").length;
  // Vertical-writing-mode titles ("Notre Rencontre", "Our Year") hug to
  // their real rendered length too — inverts the same formula
  // useFitTitleFontSize used to fit them, so the box always matches
  // whatever the text actually rendered at, not the raw stored title_h.
  const verticalTitleMeasured = containerWidth && titleWritingMode
    ? Math.max(1, measureDomTextWidth(String(title || ""), {
        fontPx: 100,
        fontWeight: titleWeight,
        fontFamily: titleFont,
        letterSpacing: "-0.025em",
        uppercase: titleUppercase,
      }))
    : 0;
  const visualTitleH =
    containerWidth && titleWritingMode
      // Floor of 0.12 avoids regressing into an unusably thin selection
      // target — a past attempt at hugging this box collapsed it to a
      // sliver that was hard to click or drag.
      ? Math.max(0.12, Math.min(titleH, (fittedTitleFontSizePx * verticalTitleMeasured / 100 / 0.92) / (containerWidth * pageAspect)))
      : containerWidth && !titleWritingMode
      ? Math.min(titleH, (fittedTitleFontSizePx * 0.95 * titleLineCount) / (containerWidth * pageAspect))
      : titleH;

  return (
    <div
      ref={containerRef}
      className={`relative w-full ${aspect} overflow-hidden`}
      style={{ background: bg, containerType: "inline-size" }}
      onClick={(e) => {
        if (!editable) return;
        // Click on cover background → select cover
        if (e.target === e.currentTarget) {
          onSelectCover && onSelectCover();
        }
      }}
      data-testid="cover-front"
    >
      <div className="absolute inset-0 grain pointer-events-none" />

      {/* Custom cover image (behind title) */}
      {coverImageUrl && (
        <img
          src={coverImageUrl}
          alt="Cover"
          className="absolute inset-x-[10%] top-[40%] w-[80%] h-[45%] object-cover pointer-events-none select-none"
          draggable={false}
        />
      )}

      {/* Title (draggable if editable) */}
      {editable ? (
        <DraggableItem
          item={{ id: "cover-title", x: titleX, y: titleY, w: titleW, h: visualTitleH }}
          onChange={(patch) => onUpdateTitle && onUpdateTitle(patch)}
          onSelect={() => onSelectTitle && onSelectTitle()}
          onDoubleClick={() => onTitleTextChange && setTitleEditing(true)}
          selected={titleSelected}
          containerRef={containerRef}
          editable={editable && !titleEditing}
          tid="cover-title"
          onDragStateChange={(d) => setDraggingId(d ? "cover-title" : null)}
        >
          {titleEditing ? (
            <textarea
              autoFocus
              value={title}
              onChange={(e) => onTitleTextChange && onTitleTextChange(e.target.value)}
              onFocus={(e) => e.target.select()}
              onPointerDown={(e) => e.stopPropagation()}
              onBlur={() => setTitleEditing(false)}
              onKeyDown={(e) => {
                if (e.key === "Escape" || e.key === "Enter") { e.currentTarget.blur(); }
                e.stopPropagation();
              }}
              className={`leading-[0.95] tracking-tight w-full h-full bg-transparent border-0 outline-none resize-none whitespace-pre-wrap ${titleUppercase ? "uppercase" : ""}`}
              style={{
                color: cover.title_color || text,
                fontFamily: titleFont,
                fontWeight: titleWeight,
                fontStyle: titleFontStyle,
                textAlign: titleTextAlign,
                fontSize: titleFontSizeStyle,
                transform: titleWritingMode === "vertical-rl" ? "rotate(180deg)" : (!titleWritingMode && titleRotation ? `rotate(${titleRotation}deg)` : undefined),
                writingMode: titleWritingMode || undefined,
                wordSpacing: titleWritingMode === "vertical-rl" ? "0.05em" : undefined,
              }}
              data-testid="cover-title-input"
            />
          ) : (
            <h1
              className="leading-[0.95] tracking-tight w-full h-full pointer-events-none select-none"
              style={{
                color: cover.title_color || text,
                fontFamily: titleFont,
                fontWeight: titleWeight,
                fontStyle: titleFontStyle,
                textAlign: titleTextAlign,
                fontSize: titleFontSizeStyle,
                transform: titleWritingMode === "vertical-rl" ? "rotate(180deg)" : (!titleWritingMode && titleRotation ? `rotate(${titleRotation}deg)` : undefined),
                writingMode: titleWritingMode || undefined,
                wordSpacing: titleWritingMode === "vertical-rl" ? "0.05em" : undefined,
                whiteSpace: titleWritingMode || titleSingleLine ? "nowrap" : undefined,
              }}
            >
              {titleWritingMode || titleSingleLine ? (
                <span className={titleUppercase ? "uppercase" : ""}>{title}</span>
              ) : (
                title.split(" ").map((w, i) => (
                  <span key={i} className={`block ${titleUppercase ? "uppercase" : ""}`}>{w}</span>
                ))
              )}
            </h1>
          )}
        </DraggableItem>
      ) : (
        <h1
          className="absolute leading-[0.95] tracking-tight overflow-hidden"
          style={{
            left: `${titleX * 100}%`,
            top: `${titleY * 100}%`,
            width: `${titleW * 100}%`,
            color: cover.title_color || text,
            fontFamily: titleFont,
            fontWeight: titleWeight,
            fontStyle: titleFontStyle,
            textAlign: titleTextAlign,
            fontSize: titleFontSizeStyle,
            transform: titleWritingMode === "vertical-rl" ? "rotate(180deg)" : (!titleWritingMode && titleRotation ? `rotate(${titleRotation}deg)` : undefined),
            writingMode: titleWritingMode || undefined,
            wordSpacing: titleWritingMode === "vertical-rl" ? "0.05em" : undefined,
            whiteSpace: titleWritingMode || titleSingleLine ? "nowrap" : undefined,
          }}
        >
          {titleWritingMode || titleSingleLine ? (
            <span className={titleUppercase ? "uppercase" : ""}>{title}</span>
          ) : (
            title.split(" ").map((w, i) => (
              <span key={i} className={`block ${titleUppercase ? "uppercase" : ""}`}>{w}</span>
            ))
          )}
        </h1>
      )}

      {/* Extra items on cover (text / shape) */}
      {extras.map((item) => {
        const isSel = selectedItemId === item.id;
        // The subtitle is meant to sit right at the title box's bottom edge,
        // sized proportionally to the title (0.58x) rather than its own
        // fixed stored font_size — that stored value was calibrated to the
        // old, smaller static title and looks undersized now that the title
        // fills the box's full width dynamically.
        const SUBTITLE_RATIO = 0.58;
        const renderItem = (() => {
          if (item.role !== "subtitle") return item;
          // Same reasoning as titleScale/spine's scale fields — the Size
          // slider used to write to item.font_size, but that value was
          // never actually read here (idealFontSize below is derived
          // purely from the title's own fitted size, ignoring it
          // entirely), so the slider had no visible effect. font_scale is
          // the real, working control, clamped so it can only shrink
          // below the auto-fit size, never risk pushing past the box the
          // overflow cap further down protects.
          const subtitleScale = Math.min(1, Math.max(0.4, item.font_scale ?? 1));
          const idealFontSize = containerWidth
            ? (fittedTitleFontSizePx / containerWidth) * REFERENCE_PAGE_PX * SUBTITLE_RATIO * subtitleScale
            : item.font_size;
          // idealFontSize above is derived purely from the title's own
          // fitted size, with no awareness of the subtitle's own box —
          // some templates (e.g. Sicily) position the subtitle in a
          // narrower, hand-placed box than the title's. Cap the font size
          // so the text never overflows that box, the same way the title
          // fits its own box, instead of letting a large title push the
          // subtitle past the edge of a box sized for a smaller font.
          let fontSize = idealFontSize;
          if (containerWidth && item.content) {
            const boxWidthPx = item.w * containerWidth;
            const measuredAtIdeal = measureDomTextWidth(item.content, {
              fontPx: idealFontSize,
              fontWeight: item.font_weight || "normal",
              fontFamily: item.font || titleFont,
              letterSpacing: "normal",
              uppercase: true, // subtitle always renders uppercase (see textTransform below)
            });
            if (measuredAtIdeal > boxWidthPx) {
              // 0.85 (was 0.96) — a wider safety margin against exactly
              // this kind of edge case: this measurement is only as
              // accurate as whatever font is actually loaded the instant
              // it runs, and the PDF export (a fresh, fast headless
              // browser render) has less natural time for that to happen
              // than the flipbook does. A tighter margin here means the
              // cap kicks in a bit sooner even if the measurement itself
              // is slightly off, rather than needing it to be exact.
              fontSize = idealFontSize * (boxWidthPx / measuredAtIdeal) * 0.85;
            }
          }
          // item.h is whatever was stored for this item — often calibrated
          // to a much smaller, static subtitle size from before this font
          // size became dynamic (proportional to the title, which can
          // render far bigger now). The box itself never grew to match,
          // so a subtitle rendering near the top of its safe font-size
          // range could be taller than the box that's supposed to contain
          // it, clipped at the bottom by that box's own overflow:hidden.
          // 1.25x is a standard line-height safety margin over the raw
          // font size; never shrinks the box below whatever was stored,
          // only grows it if the real text needs more room.
          const requiredH = (fontSize / REFERENCE_PAGE_PX) * 1.25 / pageAspect;
          const boxH = Math.max(item.h, requiredH);
          return { ...item, y: titleY + visualTitleH, h: boxH, font_size: fontSize };
        })();
        if (item.type === "text") {
          const inTextEdit = isSel && extraTextEditId === item.id;
          return (
            <DraggableItem
              key={item.id}
              item={renderItem}
              onChange={(patch) => onUpdateItem && onUpdateItem(item.id, patch)}
              onSelect={() => onSelectItem && onSelectItem(item)}
              onDoubleClick={() => setExtraTextEditId(item.id)}
              selected={isSel}
              containerRef={containerRef}
              editable={editable && !inTextEdit}
              tid={`cover-extra-${item.id}`}
              onDragStateChange={(d) => setDraggingId(d ? item.id : null)}
              extraStyle={{
                color: item.color || text,
                fontFamily: item.font || titleFont,
                fontWeight: item.font_weight || "normal",
                fontStyle: item.font_style || "normal",
                lineHeight: 1.15,
                overflow: "hidden",
                wordBreak: "break-word",
                textAlign: item.text_align || "left",
                textTransform: item.role === "subtitle" ? "uppercase" : "none",
              }}
            >
              {inTextEdit ? (
                <textarea
                  autoFocus
                  value={item.content}
                  onChange={(e) => onUpdateItem && onUpdateItem(item.id, { content: e.target.value })}
                  onFocus={(e) => e.target.select()}
                  onPointerDown={(e) => e.stopPropagation()}
                  onBlur={() => setExtraTextEditId(null)}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") { e.currentTarget.blur(); }
                    e.stopPropagation();
                  }}
                  className="whitespace-pre-wrap block w-full h-full bg-transparent border-0 outline-none resize-none"
                  style={{
                    color: "inherit",
                    font: "inherit",
                    lineHeight: "inherit",
                    // text-transform doesn't reliably inherit into a
                    // <textarea> in every browser (a long-standing quirk
                    // with form controls) — the parent's uppercase style
                    // above only ever affected the read-only AutoFitText
                    // display, never this editing field, so double-clicking
                    // a subtitle like "GREECE" to edit it showed the raw
                    // stored text ("Greece") instead of matching the
                    // uppercase look it has everywhere else.
                    textTransform: item.role === "subtitle" ? "uppercase" : "none",
                    fontSize: `${(((renderItem.font_size || 20) / REFERENCE_PAGE_PX) * 100).toFixed(2)}cqw`,
                  }}
                  data-testid={`cover-extra-input-${item.id}`}
                />
              ) : (
                <AutoFitText key={`${item.id}-${item.content}`} baseFontSize={renderItem.font_size || 20} content={item.content} />
              )}
            </DraggableItem>
          );
        }
        if (item.type === "shape") {
          return (
            <DraggableItem
              key={item.id}
              item={item}
              onChange={(patch) => onUpdateItem && onUpdateItem(item.id, patch)}
              onSelect={() => onSelectItem && onSelectItem(item)}
              selected={isSel}
              containerRef={containerRef}
              editable={editable}
              tid={`cover-shape-${item.id}`}
              onDragStateChange={(d) => setDraggingId(d ? item.id : null)}
              extraStyle={{
                background: item.fill_color || accent,
                borderRadius: item.shape_type === "circle" ? "9999px" : "0",
              }}
            >
              <div className="w-full h-full pointer-events-none" />
            </DraggableItem>
          );
        }
        if (item.type === "image") {
          const isPhoto = !!item.is_photo;
          const inCrop = isPhoto && cropItemId === item.id;
          const scale = item.scale ?? 1;
          const rotation = item.rotation || 0;
          const focalX = item.focal_x ?? 0.5;
          const focalY = item.focal_y ?? 0.5;
          const frameAspect = (item.w / item.h) * pageAspectWH(orientation);
          const photoAspect = item.photo_aspect || loadedAspects[item.id];
          return (
            <React.Fragment key={item.id}>
              <DraggableItem
                item={item}
                onChange={(patch) => onUpdateItem && onUpdateItem(item.id, patch)}
                onSelect={() => onSelectItem && onSelectItem(item)}
                selected={isSel}
                containerRef={containerRef}
                editable={editable && !inCrop}
                tid={`cover-image-${item.id}`}
                onDragStateChange={(d) => setDraggingId(d ? item.id : null)}
                extraStyle={{ overflow: "hidden" }}
              >
                {item.image_url && isPhoto ? (
                  <FramedPhoto
                    src={item.image_url}
                    frameAspect={frameAspect}
                    photoAspect={item.photo_aspect}
                    zoom={scale}
                    focalX={focalX}
                    focalY={focalY}
                    rotation={rotation}
                    onAspect={(a) => setLoadedAspects((prev) => (prev[item.id] === a ? prev : { ...prev, [item.id]: a }))}
                  />
                ) : item.image_url ? (
                  <img
                    src={item.image_url}
                    alt=""
                    className="w-full h-full pointer-events-none select-none"
                    style={{ objectFit: "contain" }}
                    draggable={false}
                  />
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center gap-1 bg-black/5 border-2 border-dashed border-current opacity-60 pointer-events-none">
                    <ImagePlus size={18} />
                    <span className="text-[9px] uppercase tracking-widest text-center px-1">Add a photo</span>
                  </div>
                )}
                {inCrop && (
                  <PhotoPanOverlay
                    focalX={focalX}
                    focalY={focalY}
                    onPan={(fx, fy) => onUpdateItem && onUpdateItem(item.id, { focal_x: fx, focal_y: fy })}
                  />
                )}
              </DraggableItem>
              {isPhoto && item.image_url && isSel && editable && !inCrop && (
                <PhotoFrameToolbar
                  x={item.x}
                  y={item.y}
                  w={item.w}
                  onEdit={() => setCropItemId(item.id)}
                  onDelete={() => onUpdateItem && onUpdateItem(item.id, { image_url: null, storage_path: null, scale: 1, rotation: 0, focal_x: 0.5, focal_y: 0.5 })}
                  hideSwap
                  hideReorder
                />
              )}
              {inCrop && (
                <PhotoEditToolbar
                  x={item.x}
                  y={item.y}
                  w={item.w}
                  scale={scale}
                  minScale={minZoom(frameAspect, photoAspect)}
                  onScaleChange={(s) => onUpdateItem && onUpdateItem(item.id, { scale: s })}
                  rotation={rotation}
                  onRotationChange={(r) => onUpdateItem && onUpdateItem(item.id, { rotation: r })}
                  onDone={() => setCropItemId(null)}
                />
              )}
            </React.Fragment>
          );
        }
        return null;
      })}
      <CenterGuides
        show={editable && !!draggingId}
        guideX={cover.align_guide_x}
        guideY={cover.align_guide_y}
      />
    </div>
  );
}
