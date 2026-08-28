import React, { useRef, useCallback, useState, useLayoutEffect, useEffect } from "react";
import { photoImageUrl } from "@/lib/api";
import { PhotoFrameToolbar, PhotoEditToolbar, PhotoPanOverlay, TextItemToolbar } from "@/components/ItemToolbars";
import LayoutPicker from "@/components/LayoutPicker";
import { ImagePlus, LayoutGrid, Type, Trash2 } from "lucide-react";

// Same reference width the backend PDF export (server.py) scales
// `title_font_size` / extra_items `font_size` against, so a value stored on
// a template renders at the same relative size here as it will in the final
// PDF. Kept as one named constant instead of the magic number 430 repeated
// inline, so the two stay easy to keep in sync.
const REFERENCE_PAGE_PX = 430;

let _measureCanvas = null;
export function measureTextWidth(text, fontPx, fontWeight, fontFamily) {
  if (!_measureCanvas) _measureCanvas = document.createElement("canvas");
  const ctx = _measureCanvas.getContext("2d");
  ctx.font = `${fontWeight || 400} ${fontPx}px ${fontFamily}`;
  return ctx.measureText(text).width;
}

let _measureEl = null;
/**
 * Measures text width using an actual hidden DOM element instead of canvas.
 * Unlike canvas.measureText(), this automatically reflects letter-spacing,
 * text-transform, and whichever font actually ended up loaded — no manual
 * per-property correction needed, and no risk of measuring against a
 * fallback font before the real one is ready.
 */
export function measureDomTextWidth(text, { fontPx, fontWeight, fontFamily, letterSpacing, uppercase }) {
  if (typeof document === "undefined") return 0;
  if (!_measureEl) {
    _measureEl = document.createElement("span");
    _measureEl.style.position = "absolute";
    _measureEl.style.visibility = "hidden";
    _measureEl.style.whiteSpace = "pre";
    _measureEl.style.top = "-9999px";
    _measureEl.style.left = "-9999px";
    _measureEl.style.pointerEvents = "none";
    document.body.appendChild(_measureEl);
  }
  _measureEl.style.fontFamily = fontFamily;
  _measureEl.style.fontWeight = fontWeight || "400";
  _measureEl.style.fontSize = `${fontPx}px`;
  _measureEl.style.letterSpacing = letterSpacing || "normal";
  _measureEl.style.textTransform = uppercase ? "uppercase" : "none";
  _measureEl.textContent = text;
  return _measureEl.getBoundingClientRect().width;
}

/**
 * Fits the cover title to its box: measures the widest word with a canvas
 * and scales the font size so it fills the full width of the title box —
 * for every template, regardless of word length. This both shrinks long
 * words (e.g. "AUSTRALIA") so they never bleed past the cover edge, and
 * grows short words (e.g. "SICILY") so they aren't left looking small in
 * an oversized box. The stored title_font_size is only used as the
 * starting point for measurement, not as a ceiling.
 */
function useFitTitleFontSize({ containerWidth, boxWidthFraction, boxHeightFraction, lineCount, text, storedFontSize, fontFamily, fontWeight, uppercase, writingMode, pageAspect, singleLine, scale }) {
  const [fontSize, setFontSize] = useState(storedFontSize || 32);

  useLayoutEffect(() => {
    if (!containerWidth || !text) return;

    if (writingMode) {
      // Vertical title (e.g. "Notre Rencontre"): fit it to the box's real
      // footprint instead of trusting the stored size blindly — the text's
      // rendered *width* becomes its vertical extent once rotated, and the
      // box's own width caps how "thick" it can safely get.
      const compute = () => {
        const REF_PX = 100;
        const lengthPx = boxHeightFraction * containerWidth * pageAspect; // box height -> px (the reading-direction length)
        const thicknessPx = boxWidthFraction * containerWidth; // box width -> px (the cap on stroke thickness)
        const measured = Math.max(
          1,
          measureDomTextWidth(String(text), {
            fontPx: REF_PX,
            fontWeight,
            fontFamily,
            letterSpacing: "-0.025em",
            uppercase,
          })
        );
        const fitted = Math.min(REF_PX * (lengthPx / measured) * 0.92, thicknessPx * 0.92);
        setFontSize(Math.max(8, fitted));
      };
      compute();
      let cancelled = false;
      if (typeof document !== "undefined" && document.fonts && document.fonts.load) {
        const spec = `${fontWeight || 400} 16px ${fontFamily}`;
        Promise.all([document.fonts.load(spec), document.fonts.ready])
          .then(() => {
            if (!cancelled) compute();
          })
          .catch(() => {});
      }
      return () => {
        cancelled = true;
      };
    }

    const compute = () => {
      const boxWidthPx = boxWidthFraction * containerWidth;
      const REF_PX = 100; // fixed reference size for measurement; only the ratio matters

      // Single-line titles ("Our Forever Journey" on one row) measure the
      // whole string at once; multi-line titles (one word per line) fit to
      // whichever individual word is widest.
      const words = singleLine ? [String(text)] : String(text).split(" ");
      const widestAtRef = Math.max(
        1,
        ...words.map((w) =>
          measureDomTextWidth(w, {
            fontPx: REF_PX,
            fontWeight,
            fontFamily,
            letterSpacing: "-0.025em", // matches the title's `tracking-tight` class
            uppercase,
          })
        )
      );

      // SAFETY is the "fill 100% of the box" baseline; `scale` (1 = fill
      // exactly, <1 shrinks, >1 grows past the box edge if pushed hard) is
      // the only thing the size slider in the right panel controls now.
      // Without a scale term here, any value the slider writes to
      // storedFontSize cancels out of this ratio algebraically — that's
      // the bug that made the slider look like it stopped doing anything.
      const SAFETY = 0.96 * (scale ?? 1);
      let fitted = REF_PX * (boxWidthPx / widestAtRef) * SAFETY;

      // Cap by the box's own height so a short word in a MULTI-line title
      // (e.g. "Our" / "Forever" / "Journey") can't grow past what the box can
      // actually hold once every line is stacked. A single-word title has no
      // such risk — capping it too would silently override the width-fill
      // goal using the stored title_h, which was sized for the old, smaller
      // static font and is often too short for a true full-width fit.
      if (boxHeightFraction && lineCount > 1) {
        const boxHeightPx = boxHeightFraction * containerWidth * pageAspect; // height = width * (page height / page width)
        const maxByHeight = (boxHeightPx / lineCount) * 0.92;
        fitted = Math.min(fitted, maxByHeight);
      }

      setFontSize(Math.max(10, fitted));
    };

    // Measure immediately for a fast first paint...
    compute();

    // ...then re-measure once the real @font-face is confirmed loaded. Since
    // this now measures a real DOM element with the same font-family, this
    // re-run is what corrects an initial fallback-font measurement — no
    // manual per-property math needed for whichever font is actually active.
    let cancelled = false;
    if (typeof document !== "undefined" && document.fonts && document.fonts.load) {
      const spec = `${fontWeight || 400} 16px ${fontFamily}`;
      Promise.all([document.fonts.load(spec), document.fonts.ready])
        .then(() => {
          if (!cancelled) compute();
        })
        .catch(() => {});
    }
    return () => {
      cancelled = true;
    };
  }, [containerWidth, boxWidthFraction, boxHeightFraction, lineCount, text, storedFontSize, fontFamily, fontWeight, uppercase, writingMode, pageAspect, singleLine, scale]);

  return fontSize;
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
 * Common draggable + resizable wrapper for items placed with normalized
 * (0-1, top-left origin) coordinates. Requires containerRef pointing to the
 * page element (so we can compute pointer position relative to it).
 *
 * Props:
 *   item         - {id, x, y, w, h, ...}
 *   onChange     - (patch) => void
 *   onSelect     - () => void
 *   selected     - bool
 *   containerRef - React ref for the page container
 *   editable     - bool
 */
export function DraggableItem({ item, onChange, onSelect, selected, containerRef, editable, children, extraStyle, tid, minW = 0.05, minH = 0.03, onDragStateChange, onDoubleClick }) {
  const dragState = useRef(null);
  const lastClickAtRef = useRef(0);

  const onPointerDown = useCallback((e) => {
    if (!editable) return;
    e.stopPropagation();
    onSelect && onSelect();
    // Manual double-click detection (two pointerdowns within 400ms) — the
    // browser's native dblclick can miss this because the toolbar appears
    // right after the first click and may intercept the second one.
    const now = Date.now();
    if (onDoubleClick && now - lastClickAtRef.current < 400) {
      lastClickAtRef.current = 0;
      onDoubleClick();
      return;
    }
    lastClickAtRef.current = now;
    if (!containerRef?.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    dragState.current = {
      mode: "move",
      startX: e.clientX,
      startY: e.clientY,
      startItemX: item.x,
      startItemY: item.y,
      rectW: rect.width,
      rectH: rect.height,
    };
    onDragStateChange && onDragStateChange(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  }, [editable, item.x, item.y, onSelect, containerRef, onDragStateChange, onDoubleClick]);

  const onResizePointerDown = useCallback((e) => {
    if (!editable) return;
    e.stopPropagation();
    onSelect && onSelect();
    if (!containerRef?.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    dragState.current = {
      mode: "resize",
      startX: e.clientX,
      startY: e.clientY,
      startItemW: item.w,
      startItemH: item.h,
      rectW: rect.width,
      rectH: rect.height,
    };
    onDragStateChange && onDragStateChange(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  }, [editable, item.w, item.h, onSelect, containerRef, onDragStateChange]);

  const onPointerMove = useCallback((e) => {
    if (!dragState.current) return;
    const ds = dragState.current;
    const dx = (e.clientX - ds.startX) / ds.rectW;
    const dy = (e.clientY - ds.startY) / ds.rectH;
    if (ds.mode === "move") {
      const nx = Math.max(0, Math.min(1 - item.w, ds.startItemX + dx));
      const ny = Math.max(0, Math.min(1 - item.h, ds.startItemY + dy));
      onChange({ x: nx, y: ny });
    } else if (ds.mode === "resize") {
      const nw = Math.max(minW, Math.min(1 - item.x, ds.startItemW + dx));
      const nh = Math.max(minH, Math.min(1 - item.y, ds.startItemH + dy));
      onChange({ w: nw, h: nh });
    }
  }, [item.w, item.h, item.x, item.y, onChange, minW, minH]);

  const onPointerUp = useCallback((e) => {
    if (dragState.current) {
      const mode = dragState.current.mode;
      dragState.current = null;
      onDragStateChange && onDragStateChange(false, mode);
      try { e.currentTarget.releasePointerCapture(e.pointerId); } catch { /* noop */ }
    }
  }, [onDragStateChange]);

  const style = {
    left: `${item.x * 100}%`,
    top: `${item.y * 100}%`,
    width: `${item.w * 100}%`,
    height: `${item.h * 100}%`,
    ...extraStyle,
  };
  const ring = editable && selected ? "outline outline-2 outline-[color:var(--coral)]" : "";
  return (
    <div
      className={`absolute ${ring} ${editable ? "cursor-move" : ""}`}
      style={style}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onDoubleClick={onDoubleClick}
      data-testid={tid}
    >
      {children}
      {editable && selected && (
        <div
          className="absolute -bottom-1.5 -right-1.5 w-4 h-4 bg-[color:var(--coral)] cursor-nwse-resize z-10 rounded-sm"
          onPointerDown={onResizePointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          data-testid={`${tid}-resize`}
          title="Redimensionner"
        />
      )}
    </div>
  );
}

/**
 * AlbumPage renders one printable page with draggable + resizable items.
 */
export function AlbumPage({
  page,
  orientation = "portrait",
  pageIndex = 0,
  highRes = false,
  editable = false,
  onSelectItem,
  onUpdateItem,
  onDeleteItem,
  swapSourceItemId,
  onSwapAction,
  onAddPhotoAt,
  onReplacePhoto,
  onReorderLayer,
  onApplyLayout,
  onDeletePage,
  placingPhotoId,
  onPhotoPlaced,
  selectedItemId,
  cropMode = false,
  onEnterCrop,
  onExitCrop,
  placingText = false,
  onPlaceText,
  onStartAddText,
  autoEditItemId,
  onTextEditHandled,
}) {
  const containerRef = useRef(null);
  const aspect = orientation === "landscape" ? "aspect-[1.414/1]" : "aspect-[1/1.414]";
  const items = page?.items || [];
  const [draggingId, setDraggingId] = useState(null);
  const [textEditId, setTextEditId] = useState(null);
  const [showLayoutPicker, setShowLayoutPicker] = useState(false);
  const itemsRef = useRef(items);
  itemsRef.current = items;

  React.useEffect(() => {
    if (autoEditItemId && items.some((it) => it.id === autoEditItemId)) {
      setTextEditId(autoEditItemId);
      onTextEditHandled && onTextEditHandled();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoEditItemId]);

  const handlePhotoDragStateChange = (item, isDragging) => {
    setDraggingId(isDragging ? item.id : null);
  };

  const handleDragOver = (e) => {
    if (!editable) return;
    e.preventDefault();
  };

  const handleDrop = (e) => {
    if (!editable) return;
    e.preventDefault();
    const photoId = e.dataTransfer.getData("text/photo-id");
    if (!photoId || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const nx = (e.clientX - rect.left) / rect.width;
    const ny = (e.clientY - rect.top) / rect.height;
    // Dropped onto an existing photo frame → replace its content.
    const target = items.find((it) => it.type === "photo" && nx >= it.x && nx <= it.x + it.w && ny >= it.y && ny <= it.y + it.h);
    if (target) {
      onReplacePhoto && onReplacePhoto(target.id, photoId);
    } else {
      // Dropped on empty space → create a new frame centered on the drop point.
      const w = 0.35, h = 0.3;
      onAddPhotoAt && onAddPhotoAt(photoId, {
        x: Math.min(Math.max(nx - w / 2, 0), 1 - w),
        y: Math.min(Math.max(ny - h / 2, 0), 1 - h),
        w,
        h,
      });
    }
  };

  const handleClick = (e) => {
    if (swapSourceItemId) {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const nx = (e.clientX - rect.left) / rect.width;
      const ny = (e.clientY - rect.top) / rect.height;
      const target = itemsRef.current.find(
        (it) => it.type === "photo" && it.id !== swapSourceItemId && nx >= it.x && nx <= it.x + it.w && ny >= it.y && ny <= it.y + it.h
      );
      onSwapAction && onSwapAction(pageIndex, target ? target.id : null);
      return;
    }
    if (placingPhotoId) {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const nx = (e.clientX - rect.left) / rect.width;
      const ny = (e.clientY - rect.top) / rect.height;
      const target = itemsRef.current.find(
        (it) => it.type === "photo" && nx >= it.x && nx <= it.x + it.w && ny >= it.y && ny <= it.y + it.h
      );
      if (target) {
        onReplacePhoto && onReplacePhoto(target.id, placingPhotoId);
      } else {
        const w = 0.35, h = 0.3;
        onAddPhotoAt && onAddPhotoAt(placingPhotoId, {
          x: Math.min(Math.max(nx - w / 2, 0), 1 - w),
          y: Math.min(Math.max(ny - h / 2, 0), 1 - h),
          w,
          h,
        });
      }
      onPhotoPlaced && onPhotoPlaced();
      return;
    }
    if (e.target !== e.currentTarget) return; // ignore clicks that landed on an existing item
    if (placingText) {
      const rect = containerRef.current.getBoundingClientRect();
      const nx = (e.clientX - rect.left) / rect.width;
      const ny = (e.clientY - rect.top) / rect.height;
      onPlaceText && onPlaceText({ x: Math.min(Math.max(nx - 0.25, 0), 0.7), y: Math.min(Math.max(ny - 0.04, 0), 0.92) });
    } else {
      onSelectItem && onSelectItem(null);
    }
  };

  return (
    <div
      ref={containerRef}
      className={`relative w-full ${aspect} bg-[color:var(--paper)] ${placingText ? "cursor-text" : ""} ${placingPhotoId ? "cursor-copy" : ""}`}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      onClick={handleClick}
    >
      <div className="absolute inset-0 grain pointer-events-none" />
      {items.map((item) => {
        const isSel = selectedItemId === item.id;
        if (item.type === "photo") {
          const scale = Math.max(item.scale || 1, 1);
          const focalX = item.focal_x ?? 0.5;
          const focalY = item.focal_y ?? 0.5;
          const rotation = item.rotation || 0;
          const inCrop = isSel && cropMode;
          const isSwapSource = swapSourceItemId === item.id;
          const isEmpty = !item.photo_id;
          return (
            <React.Fragment key={item.id}>
              <DraggableItem
                item={item}
                onChange={(patch) => onUpdateItem && onUpdateItem(item.id, patch)}
                onSelect={() => onSelectItem && onSelectItem(item)}
                onDoubleClick={() => editable && !isEmpty && onSwapAction && onSwapAction(pageIndex, item.id)}
                selected={isSel}
                containerRef={containerRef}
                editable={editable && !inCrop}
                tid={`page-photo-${item.id}`}
                onDragStateChange={(d, mode) => handlePhotoDragStateChange(item, d, mode)}
                extraStyle={{ overflow: "hidden", outline: isSwapSource ? "2px dashed var(--coral)" : undefined, outlineOffset: isSwapSource ? "-2px" : undefined }}
              >
                {isEmpty ? (
                  <div className="w-full h-full flex flex-col items-center justify-center gap-2 bg-[color:var(--editor-canvas)] border-2 border-dashed border-[color:var(--ink)]/20 pointer-events-none">
                    <ImagePlus size={22} className="text-[color:var(--muted)]" />
                    <span className="text-[10px] text-[color:var(--muted)] uppercase tracking-widest text-center px-2">Drop a photo here</span>
                  </div>
                ) : (
                  <img
                    src={photoImageUrl(item.photo_id, highRes ? "print" : "medium")}
                    alt=""
                    className="w-full h-full pointer-events-none select-none"
                    style={{
                      objectFit: "cover",
                      transform: `scale(${scale}) rotate(${rotation}deg)`,
                      transformOrigin: `${focalX * 100}% ${focalY * 100}%`,
                      objectPosition: `${focalX * 100}% ${focalY * 100}%`,
                    }}
                    draggable={false}
                  />
                )}
                {inCrop && !isEmpty && (
                  <PhotoPanOverlay
                    focalX={focalX}
                    focalY={focalY}
                    onPan={(fx, fy) => onUpdateItem && onUpdateItem(item.id, { focal_x: fx, focal_y: fy })}
                  />
                )}
              </DraggableItem>
              {isSel && editable && !inCrop && !isEmpty && (
                <PhotoFrameToolbar
                  x={item.x}
                  y={item.y}
                  w={item.w}
                  onEdit={() => onEnterCrop && onEnterCrop(item.id)}
                  onSwap={() => onSwapAction && onSwapAction(pageIndex, isSwapSource ? null : item.id)}
                  isSwapping={isSwapSource}
                  onBringForward={() => onReorderLayer && onReorderLayer(item.id, "forward")}
                  onSendBackward={() => onReorderLayer && onReorderLayer(item.id, "backward")}
                  onDelete={() => onDeleteItem && onDeleteItem(item.id)}
                />
              )}
              {isSel && editable && isEmpty && (
                <PhotoFrameToolbar
                  x={item.x}
                  y={item.y}
                  w={item.w}
                  onEdit={() => {}}
                  onSwap={() => {}}
                  isSwapping={false}
                  onBringForward={() => onReorderLayer && onReorderLayer(item.id, "forward")}
                  onSendBackward={() => onReorderLayer && onReorderLayer(item.id, "backward")}
                  onDelete={() => onDeleteItem && onDeleteItem(item.id)}
                  emptyFrame
                />
              )}
              {inCrop && !isEmpty && (
                <PhotoEditToolbar
                  x={item.x}
                  y={item.y}
                  w={item.w}
                  scale={scale}
                  onScaleChange={(s) => onUpdateItem && onUpdateItem(item.id, { scale: s })}
                  rotation={rotation}
                  onRotationChange={(r) => onUpdateItem && onUpdateItem(item.id, { rotation: r })}
                  onDone={() => onExitCrop && onExitCrop()}
                />
              )}
            </React.Fragment>
          );
        }
        if (item.type === "text") {
          const inTextEdit = isSel && textEditId === item.id;
          return (
            <React.Fragment key={item.id}>
              <DraggableItem
                item={item}
                onChange={(patch) => onUpdateItem && onUpdateItem(item.id, patch)}
                onSelect={() => onSelectItem && onSelectItem(item)}
                onDoubleClick={() => setTextEditId(item.id)}
                selected={isSel}
                containerRef={containerRef}
                editable={editable && !inTextEdit}
                tid={`page-text-${item.id}`}
                onDragStateChange={(d) => setDraggingId(d ? item.id : null)}
                extraStyle={{
                  color: item.color || "#1A1A17",
                  fontFamily: item.font || "Cormorant Garamond, serif",
                  fontSize: `${item.font_size || 16}px`,
                  fontWeight: item.font_weight || "normal",
                  fontStyle: item.font_style || "normal",
                  lineHeight: 1.15,
                  overflow: "hidden",
                  wordBreak: "break-word",
                  padding: "2px 0",
                  textAlign: item.text_align || "left",
                }}
              >
                {inTextEdit ? (
                  <textarea
                    autoFocus
                    value={item.content}
                    onChange={(e) => onUpdateItem && onUpdateItem(item.id, { content: e.target.value })}
                    onFocus={(e) => e.target.select()}
                    onPointerDown={(e) => e.stopPropagation()}
                    onBlur={() => setTextEditId(null)}
                    onKeyDown={(e) => {
                      if (e.key === "Escape") { e.currentTarget.blur(); }
                      e.stopPropagation();
                    }}
                    className="whitespace-pre-wrap block w-full h-full bg-transparent border-0 outline-none resize-none"
                    style={{ color: "inherit", font: "inherit", lineHeight: "inherit" }}
                    data-testid={`page-text-input-${item.id}`}
                  />
                ) : (
                  <span className="whitespace-pre-wrap block w-full h-full pointer-events-none select-none">
                    {item.content}
                  </span>
                )}
              </DraggableItem>
              {isSel && editable && (
                <TextItemToolbar
                  x={item.x}
                  y={item.y}
                  w={item.w}
                  item={item}
                  onChange={(patch) => onUpdateItem && onUpdateItem(item.id, patch)}
                  onDelete={() => onDeleteItem && onDeleteItem(item.id)}
                />
              )}
            </React.Fragment>
          );
        }
        return null;
      })}
      <CenterGuides
        show={editable && !!draggingId}
        guideX={page?.align_guide_x}
        guideY={page?.align_guide_y}
      />
      {editable && (onApplyLayout || onStartAddText || onDeletePage) && (
        <div className={`absolute top-1/2 -translate-y-1/2 ${pageIndex % 2 === 0 ? "-right-9" : "-left-9"} z-30 flex flex-col gap-2`}>
          {onApplyLayout && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowLayoutPicker(true);
              }}
              data-testid={`page-layout-btn-${pageIndex}`}
              className="flex flex-col items-center gap-1 bg-[color:var(--coral)] text-[color:var(--paper)] px-1.5 py-2 hover:brightness-110 transition-all shadow-md"
              title="Change this page's layout — how many photos it holds and how they're arranged"
            >
              <LayoutGrid size={13} />
            </button>
          )}
          {onStartAddText && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onStartAddText();
              }}
              data-testid={`page-add-text-btn-${pageIndex}`}
              className="flex flex-col items-center gap-1 bg-[color:var(--coral)] text-[color:var(--paper)] px-1.5 py-2 hover:brightness-110 transition-all shadow-md"
              title="Add a text box to this page — click where you want it to go"
            >
              <Type size={13} />
            </button>
          )}
          {onDeletePage && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                if (window.confirm("Delete this whole page? Any photos on it stay in your library — you'll find them under \"All your photos\" to place elsewhere.")) {
                  onDeletePage();
                }
              }}
              data-testid={`page-delete-btn-${pageIndex}`}
              className="flex flex-col items-center gap-1 bg-[color:var(--coral)] text-[color:var(--paper)] px-1.5 py-2 hover:brightness-110 transition-all shadow-md"
              title="Delete this whole page"
            >
              <Trash2 size={13} />
            </button>
          )}
        </div>
      )}
      {showLayoutPicker && (
        <LayoutPicker
          onClose={() => setShowLayoutPicker(false)}
          onChoose={(patternName) => {
            onApplyLayout(patternName);
            setShowLayoutPicker(false);
          }}
        />
      )}
    </div>
  );
}

/**
 * Alignment guide lines shown while dragging an item — appear when it lines
 * up with the page center OR with another element on the page (matching
 * edge/edge, center/center, edge/center...), at whatever position that is.
 */
function CenterGuides({ show, guideX, guideY }) {
  if (!show) return null;
  return (
    <>
      {guideX != null && (
        <div className="absolute top-0 bottom-0 w-px bg-[color:var(--coral)] pointer-events-none z-30" style={{ left: `${guideX * 100}%` }} />
      )}
      {guideY != null && (
        <div className="absolute left-0 right-0 h-px bg-[color:var(--coral)] pointer-events-none z-30" style={{ top: `${guideY * 100}%` }} />
      )}
    </>
  );
}

/**
 * Renders a cover text item at a target font size, then checks the
 * ACTUAL rendered element for overflow (scrollWidth/scrollHeight vs
 * clientWidth/clientHeight) and shrinks it if it doesn't fit.
 *
 * This exists because every earlier attempt at this problem — measuring
 * text in a hidden span ahead of time, waiting for document.fonts.ready
 * before measuring, explicitly pre-loading specific fonts — was a
 * *prediction* of what the real render would look like, made before that
 * render happened. Each prediction turned out wrong at least once (a
 * subtitle still clipped in the exported PDF despite every one of those
 * safeguards). Checking the real, already-painted DOM node instead of
 * predicting it can't be wrong the same way, because it isn't a
 * prediction — it's the actual measurement of what's actually on screen,
 * whatever font metrics or loading timing produced it.
 */
function AutoFitText({ baseFontSize, content }) {
  const ref = useRef(null);
  const [scale, setScale] = useState(1);
  const attemptsRef = useRef(0);
  // Registers itself as "still possibly correcting" on window while it
  // might need another overflow-correction pass, and un-registers once a
  // render finds no overflow (or gives up at the attempt cap). This is
  // what PrintAlbum.jsx now actually waits on before letting Playwright
  // capture the page — a fixed delay (tried at 500ms, then 1.2s) kept
  // guessing wrong about how long this takes, because it isn't a fixed
  // amount of time: it's however many render-and-remeasure cycles this
  // particular text needs, which varies by word and by how differently
  // sized the print page's physical @page layout is from whatever
  // context it was last measured in.
  const registeredRef = useRef(false);
  const markPending = () => {
    if (registeredRef.current) return;
    registeredRef.current = true;
    if (typeof window !== "undefined") window.__autoFitPending = (window.__autoFitPending || 0) + 1;
  };
  const markSettled = () => {
    if (!registeredRef.current) return;
    registeredRef.current = false;
    if (typeof window !== "undefined") window.__autoFitPending = Math.max(0, (window.__autoFitPending || 0) - 1);
  };

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !el.clientWidth || !el.clientHeight) {
      markSettled();
      return;
    }
    if (attemptsRef.current > 6) {
      // safety cap — stops any pathological back-and-forth from ever
      // looping forever, and releases the pending flag so a genuinely
      // unfittable case can't block the print export indefinitely
      markSettled();
      return;
    }
    const overflowX = el.scrollWidth / el.clientWidth;
    const overflowY = el.scrollHeight / el.clientHeight;
    const overflow = Math.max(overflowX, overflowY);
    if (overflow > 1.02 && scale > 0.3) {
      markPending();
      attemptsRef.current += 1;
      setScale((s) => Math.max(0.3, (s / overflow) * 0.97));
    } else {
      markSettled();
    }
  });

  useEffect(() => markSettled, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <span
      ref={ref}
      className="whitespace-pre-wrap block w-full h-full pointer-events-none select-none"
      style={{ fontSize: `${(((baseFontSize * scale) / REFERENCE_PAGE_PX) * 100).toFixed(2)}cqw` }}
    >
      {content}
    </span>
  );
}

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
  const titleX = cover.title_x ?? 0.08;
  const titleY = cover.title_y ?? 0.08;
  const titleW = cover.title_w ?? 0.84;
  const titleH = cover.title_h ?? 0.28;
  const titleFontSize = cover.title_font_size || null;
  const titleRotation = cover.title_rotation || 0;
  const titleWritingMode = cover.title_writing_mode || null; // "vertical-rl" keeps the box's own footprint, unlike rotate() which pivots around the box's center
  const titleUppercase = cover.title_uppercase !== false;
  const titleFontStyle = cover.title_font_style || "normal";
  const titleSingleLine = !!cover.title_single_line;
  const titleTextAlign = cover.title_text_align || "left";
  const extras = cover.extra_items || [];
  const [draggingId, setDraggingId] = useState(null);
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
          const scale = Math.max(item.scale || 1, 1);
          const rotation = item.rotation || 0;
          const focalX = item.focal_x ?? 0.5;
          const focalY = item.focal_y ?? 0.5;
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
                {item.image_url ? (
                  <img
                    src={item.image_url}
                    alt=""
                    className="w-full h-full pointer-events-none select-none"
                    style={
                      isPhoto
                        ? {
                            objectFit: "cover",
                            transform: `scale(${scale}) rotate(${rotation}deg)`,
                            transformOrigin: `${focalX * 100}% ${focalY * 100}%`,
                            objectPosition: `${focalX * 100}% ${focalY * 100}%`,
                          }
                        : { objectFit: "contain" }
                    }
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

export function CoverBackPage({
  template,
  country,
  year,
  orientation,
  cover = {},
  editable = false,
  onSelectItem,
  onUpdateItem,
  onSelectCover,
  selectedItemId,
}) {
  const containerRef = useRef(null);
  const aspect = orientation === "landscape" ? "aspect-[1.414/1]" : "aspect-[1/1.414]";
  const bg = cover.bg_color || template.bg;
  const text = cover.text_color || template.text;
  const accent = cover.accent_color || template.accent;
  const extras = cover.back_extra_items || [];
  const [draggingId, setDraggingId] = useState(null);
  const [backTextEditId, setBackTextEditId] = useState(null);
  return (
    <div
      ref={containerRef}
      className={`relative w-full ${aspect} flex flex-col items-center justify-between p-8`}
      style={{ background: bg, containerType: "inline-size" }}
      onClick={(e) => {
        if (!editable) return;
        if (e.target === e.currentTarget) onSelectCover && onSelectCover();
      }}
      data-testid="cover-back"
    >
      <div className="absolute inset-0 grain pointer-events-none" />
      <div />
      {extras.length === 0 && !cover.hide_back_text && (
        <div className="text-center">
          <div className="font-sans font-semibold tracking-[0.32em] uppercase" style={{ color: text, fontSize: "clamp(10px, 3.2cqw, 18px)" }}>
            {country || ""}
          </div>
        </div>
      )}
      {/* Brand mark — always shown, independent of extras entirely (not
          gated by extras.length, unlike the country fallback above), and
          never part of the extras array itself — it isn't a selectable,
          editable, or deletable item the way everything else on this page
          is. It used to be a regular (removable) back_extra_item with its
          content just swapped to "Everbook" — that meant it could be
          deleted like any other text, which defeats the point of a brand
          mark that's supposed to always be there. */}
      <div className="font-sans text-xs tracking-widest pointer-events-none select-none" style={{ color: text }}>
        Everbook
      </div>

      {extras.map((item) => {
        const isSel = selectedItemId === item.id;
        if (item.type === "text") {
          const inTextEdit = isSel && backTextEditId === item.id;
          return (
            <DraggableItem
              key={item.id}
              item={item}
              onChange={(patch) => onUpdateItem && onUpdateItem(item.id, patch)}
              onSelect={() => onSelectItem && onSelectItem(item)}
              onDoubleClick={() => setBackTextEditId(item.id)}
              selected={isSel}
              containerRef={containerRef}
              editable={editable && !inTextEdit}
              tid={`cover-back-text-${item.id}`}
              onDragStateChange={(d) => setDraggingId(d ? item.id : null)}
              extraStyle={{
                color: item.color || text,
                fontFamily: item.font || "'Manrope', sans-serif",
                fontSize: `${(((item.font_size || 16) / REFERENCE_PAGE_PX) * 100).toFixed(2)}cqw`,
                fontWeight: item.font_weight || "normal",
                fontStyle: item.font_style || "normal",
                lineHeight: 1.15,
                overflow: "hidden",
                wordBreak: "break-word",
                textAlign: item.text_align || "left",
              }}
            >
              {inTextEdit ? (
                <textarea
                  autoFocus
                  value={item.content}
                  onChange={(e) => onUpdateItem && onUpdateItem(item.id, { content: e.target.value })}
                  onFocus={(e) => e.target.select()}
                  onPointerDown={(e) => e.stopPropagation()}
                  onBlur={() => setBackTextEditId(null)}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") { e.currentTarget.blur(); }
                    e.stopPropagation();
                  }}
                  className="whitespace-pre-wrap block w-full h-full bg-transparent border-0 outline-none resize-none"
                  style={{ color: "inherit", font: "inherit", lineHeight: "inherit" }}
                  data-testid={`cover-back-text-input-${item.id}`}
                />
              ) : (
                <span className="whitespace-pre-wrap block w-full h-full pointer-events-none select-none">
                  {item.content}
                </span>
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
              tid={`cover-back-shape-${item.id}`}
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
          return (
            <DraggableItem
              key={item.id}
              item={item}
              onChange={(patch) => onUpdateItem && onUpdateItem(item.id, patch)}
              onSelect={() => onSelectItem && onSelectItem(item)}
              selected={isSel}
              containerRef={containerRef}
              editable={editable}
              tid={`cover-back-image-${item.id}`}
              onDragStateChange={(d) => setDraggingId(d ? item.id : null)}
            >
              {item.image_url ? (
                <img
                  src={item.image_url}
                  alt=""
                  className="w-full h-full object-contain pointer-events-none select-none"
                  draggable={false}
                />
              ) : (
                <div className="w-full h-full flex flex-col items-center justify-center gap-1 bg-black/5 border-2 border-dashed border-current opacity-60 pointer-events-none">
                  <ImagePlus size={18} />
                  <span className="text-[9px] uppercase tracking-widest text-center px-1">Add a photo</span>
                </div>
              )}
            </DraggableItem>
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

function getShape(illustration, color) {
  const size = 200;
  switch (illustration) {
    case "circle":
      return (<svg viewBox="0 0 100 100" width={size} height={size}><circle cx="50" cy="50" r="32" fill={color} /></svg>);
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
      return (<svg viewBox="0 0 100 100" width={size} height={size}><path d="M20 80 C 20 40 45 15 80 20 C 78 55 55 80 20 80 Z" fill={color} /></svg>);
    case "wave":
      return (<svg viewBox="0 0 100 100" width={size} height={size} fill="none" stroke={color} strokeWidth="4" strokeLinecap="round"><path d="M10 40 Q 30 20 50 40 T 90 40" /><path d="M10 55 Q 30 35 50 55 T 90 55" /><path d="M10 70 Q 30 50 50 70 T 90 70" /></svg>);
    case "sun":
      return (<svg viewBox="0 0 100 100" width={size} height={size}><circle cx="50" cy="55" r="22" fill={color} /><g stroke={color} strokeWidth="3" strokeLinecap="round"><line x1="50" y1="15" x2="50" y2="25" /><line x1="50" y1="85" x2="50" y2="95" /><line x1="15" y1="55" x2="25" y2="55" /><line x1="75" y1="55" x2="85" y2="55" /></g></svg>);
    case "mountain":
      return (<svg viewBox="0 0 100 100" width={size} height={size}><path d="M5 80 L 30 40 L 50 65 L 70 30 L 95 80 Z" fill={color} /></svg>);
    case "bird":
      return (<svg viewBox="0 0 100 100" width={size} height={size}><path d="M15 55 Q 30 30 50 45 Q 60 35 75 40 Q 85 50 80 65 Q 60 75 40 68 Q 22 65 15 55 Z" fill={color} /></svg>);
    default:
      return null;
  }
}
