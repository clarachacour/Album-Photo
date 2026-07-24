import React, { useRef } from "react";
import { DraggableItem } from "@/components/AlbumPage";

/**
 * The book spine — shown between the back and front cover panels.
 * Title and year always mirror the real book title/year (a spine can't say
 * something different from the cover), but — like every other text on the
 * cover — they can be dragged to reposition, resized, and restyled (font,
 * size), or hidden entirely.
 */
export function CoverSpine({ title, year, template, cover = {}, editable = false, selectedZone, onSelectTitle, onSelectYear, onUpdateCover }) {
  const containerRef = useRef(null);
  const bg = cover.bg_color || template.bg;
  const text = cover.text_color || template.text;

  const titleItem = {
    id: "spine-title",
    x: 0,
    y: cover.spine_title_y ?? 0.08,
    w: 1,
    h: cover.spine_title_h ?? 0.42,
  };
  const yearItem = {
    id: "spine-year",
    x: 0,
    y: cover.spine_year_y ?? 0.82,
    w: 1,
    h: cover.spine_year_h ?? 0.14,
  };

  return (
    <div ref={containerRef} className="relative h-full" style={{ background: bg }}>
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
            className="w-full h-full flex items-center justify-center opacity-90 tracking-[0.3em] font-sans font-semibold uppercase overflow-hidden pointer-events-none select-none"
            style={{
              color: text,
              writingMode: "vertical-rl",
              transform: "rotate(180deg)",
              fontSize: `${cover.spine_title_size || 9}px`,
              fontFamily: cover.spine_title_font || "'Manrope', sans-serif",
            }}
          >
            {title || "Album"}
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
            className="w-full h-full flex items-center justify-center font-sans font-semibold tracking-widest overflow-hidden pointer-events-none select-none"
            style={{
              color: text,
              writingMode: "vertical-rl",
              transform: "rotate(180deg)",
              fontSize: `${cover.spine_year_size || 9}px`,
              fontFamily: cover.spine_year_font || "'Manrope', sans-serif",
            }}
          >
            {year || ""}
          </div>
        </DraggableItem>
      )}
    </div>
  );
}