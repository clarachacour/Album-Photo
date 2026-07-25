import React, { useRef, useCallback } from "react";
import { photoImageUrl } from "@/lib/api";

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
export function DraggableItem({ item, onChange, onSelect, selected, containerRef, editable, children, extraStyle, tid, minW = 0.05, minH = 0.03 }) {
  const dragState = useRef(null);

  const onPointerDown = useCallback((e) => {
    if (!editable) return;
    e.stopPropagation();
    onSelect && onSelect();
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
    e.currentTarget.setPointerCapture(e.pointerId);
  }, [editable, item.x, item.y, onSelect, containerRef]);

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
    e.currentTarget.setPointerCapture(e.pointerId);
  }, [editable, item.w, item.h, onSelect, containerRef]);

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
      dragState.current = null;
      try { e.currentTarget.releasePointerCapture(e.pointerId); } catch { /* noop */ }
    }
  }, []);

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
  editable = false,
  onSelectItem,
  onUpdateItem,
  selectedItemId,
}) {
  const containerRef = useRef(null);
  const aspect = orientation === "landscape" ? "aspect-[1.414/1]" : "aspect-[1/1.414]";
  const items = page?.items || [];

  return (
    <div ref={containerRef} className={`relative w-full ${aspect} bg-[color:var(--paper)] overflow-hidden`}>
      <div className="absolute inset-0 grain pointer-events-none" />
      {items.map((item) => {
        const isSel = selectedItemId === item.id;
        if (item.type === "photo") {
          const scale = item.scale || 1;
          const focalX = item.focal_x ?? 0.5;
          const focalY = item.focal_y ?? 0.5;
          return (
            <DraggableItem
              key={item.id}
              item={item}
              onChange={(patch) => onUpdateItem && onUpdateItem(item.id, patch)}
              onSelect={() => onSelectItem && onSelectItem(item)}
              selected={isSel}
              containerRef={containerRef}
              editable={editable}
              tid={`page-photo-${item.id}`}
              extraStyle={{ overflow: "hidden" }}
            >
              <img
                src={photoImageUrl(item.photo_id)}
                alt=""
                className="w-full h-full object-cover pointer-events-none select-none"
                style={{
                  transform: `scale(${scale})`,
                  transformOrigin: `${focalX * 100}% ${focalY * 100}%`,
                  objectPosition: `${focalX * 100}% ${focalY * 100}%`,
                }}
                draggable={false}
              />
            </DraggableItem>
          );
        }
        if (item.type === "text") {
          return (
            <DraggableItem
              key={item.id}
              item={item}
              onChange={(patch) => onUpdateItem && onUpdateItem(item.id, patch)}
              onSelect={() => onSelectItem && onSelectItem(item)}
              selected={isSel}
              containerRef={containerRef}
              editable={editable}
              tid={`page-text-${item.id}`}
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
              }}
            >
              <span className="whitespace-pre-wrap block w-full h-full pointer-events-none select-none">
                {item.content}
              </span>
            </DraggableItem>
          );
        }
        return null;
      })}
    </div>
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
  onSelectCover,
  selectedItemId,
  titleSelected,
}) {
  const containerRef = useRef(null);
  const aspect = orientation === "landscape" ? "aspect-[1.414/1]" : "aspect-[1/1.414]";
  const bg = cover.bg_color || template.bg;
  const accent = cover.accent_color || template.accent;
  const text = cover.text_color || template.text;
  const titleFont = cover.title_font || "'Baloo 2', sans-serif";
  const titleWeight = cover.title_font_weight || "800";
  const titleX = cover.title_x ?? 0.08;
  const titleY = cover.title_y ?? 0.08;
  const titleW = cover.title_w ?? 0.84;
  const titleFontSize = cover.title_font_size || null;
  const SVGShape = getShape(template.illustration, accent);
  const extras = cover.extra_items || [];
  const hasImageExtra = extras.some((it) => it.type === "image");

  return (
    <div
      ref={containerRef}
      className={`relative w-full ${aspect} overflow-hidden`}
      style={{ background: bg }}
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
      {!coverImageUrl && !hasImageExtra && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="opacity-100">{SVGShape}</div>
        </div>
      )}

      {/* Title (draggable if editable) */}
      {editable ? (
        <DraggableItem
          item={{ id: "cover-title", x: titleX, y: titleY, w: titleW, h: 0.28 }}
          onChange={(patch) => onUpdateTitle && onUpdateTitle(patch)}
          onSelect={() => onSelectTitle && onSelectTitle()}
          selected={titleSelected}
          containerRef={containerRef}
          editable={editable}
          tid="cover-title"
        >
          <h1
            className="leading-[0.95] tracking-tight w-full h-full pointer-events-none select-none"
            style={{
              color: text,
              fontFamily: titleFont,
              fontWeight: titleWeight,
              fontSize: titleFontSize ? `${titleFontSize}px` : "clamp(28px, 6vw, 64px)",
            }}
          >
            {title.split(" ").map((w, i) => (
              <span key={i} className="block uppercase">{w}</span>
            ))}
          </h1>
        </DraggableItem>
      ) : (
        <h1
          className="absolute leading-[0.95] tracking-tight"
          style={{
            left: `${titleX * 100}%`,
            top: `${titleY * 100}%`,
            width: `${titleW * 100}%`,
            color: text,
            fontFamily: titleFont,
            fontWeight: titleWeight,
            fontSize: titleFontSize ? `${titleFontSize}px` : "clamp(28px, 6vw, 64px)",
          }}
        >
          {title.split(" ").map((w, i) => (
            <span key={i} className="block uppercase">{w}</span>
          ))}
        </h1>
      )}

      {/* Extra items on cover (text / shape) */}
      {extras.map((item) => {
        const isSel = selectedItemId === item.id;
        if (item.type === "text") {
          return (
            <DraggableItem
              key={item.id}
              item={item}
              onChange={(patch) => onUpdateItem && onUpdateItem(item.id, patch)}
              onSelect={() => onSelectItem && onSelectItem(item)}
              selected={isSel}
              containerRef={containerRef}
              editable={editable}
              tid={`cover-extra-${item.id}`}
              extraStyle={{
                color: item.color || text,
                fontFamily: item.font || titleFont,
                fontSize: `${item.font_size || 20}px`,
                fontWeight: item.font_weight || "normal",
                fontStyle: item.font_style || "normal",
                lineHeight: 1.15,
                overflow: "hidden",
                wordBreak: "break-word",
              }}
            >
              <span className="whitespace-pre-wrap block w-full h-full pointer-events-none select-none">
                {item.content}
              </span>
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
              tid={`cover-image-${item.id}`}
            >
              <img
                src={item.image_url}
                alt=""
                className="w-full h-full object-contain pointer-events-none select-none"
                draggable={false}
              />
            </DraggableItem>
          );
        }
        return null;
      })}
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
  return (
    <div
      ref={containerRef}
      className={`relative w-full ${aspect} overflow-hidden flex flex-col items-center justify-between p-8`}
      style={{ background: bg }}
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
          <div className="font-sans font-semibold tracking-[0.32em] uppercase" style={{ color: text, fontSize: "clamp(12px, 1.6vw, 18px)" }}>
            {country || ""}
          </div>
        </div>
      )}
      {extras.length === 0 && (
        <div className="font-sans text-xs tracking-widest" style={{ color: text }}>
          {year || ""}
        </div>
      )}

      {extras.map((item) => {
        const isSel = selectedItemId === item.id;
        if (item.type === "text") {
          return (
            <DraggableItem
              key={item.id}
              item={item}
              onChange={(patch) => onUpdateItem && onUpdateItem(item.id, patch)}
              onSelect={() => onSelectItem && onSelectItem(item)}
              selected={isSel}
              containerRef={containerRef}
              editable={editable}
              tid={`cover-back-text-${item.id}`}
              extraStyle={{
                color: item.color || text,
                fontFamily: item.font || "'Manrope', sans-serif",
                fontSize: `${item.font_size || 16}px`,
                fontWeight: item.font_weight || "normal",
                fontStyle: item.font_style || "normal",
                lineHeight: 1.15,
                overflow: "hidden",
                wordBreak: "break-word",
              }}
            >
              <span className="whitespace-pre-wrap block w-full h-full pointer-events-none select-none">
                {item.content}
              </span>
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
            >
              <img
                src={item.image_url}
                alt=""
                className="w-full h-full object-contain pointer-events-none select-none"
                draggable={false}
              />
            </DraggableItem>
          );
        }
        return null;
      })}
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