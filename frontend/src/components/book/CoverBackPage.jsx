import React, { useRef, useState } from "react";
import { ImagePlus } from "lucide-react";
import { CenterGuides } from "@/components/book/CenterGuides";
import { DraggableItem } from "@/components/book/DraggableItem";
import { REFERENCE_PAGE_PX } from "@/components/book/textMeasure";

export function CoverBackPage({
  template,
  country,
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
