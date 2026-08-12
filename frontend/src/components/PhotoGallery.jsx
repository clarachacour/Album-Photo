import React from "react";
import { photoImageUrl } from "@/lib/api";
import { Check } from "lucide-react";

/**
 * Shows every photo uploaded to the album — including the ones the AI didn't
 * pick for the layout — so the user can place a missing one onto a page.
 * Two ways to do that: drag it (works fine when the book is close by), or
 * click it to "arm" it, then click any frame or empty spot on any page in
 * the book to drop it there — no dragging needed, so it's never blocked by
 * the book being out of reach while scrolling.
 */
export default function PhotoGallery({ photos, placedPhotoIds, selectedPhotoId, onSelectPhoto }) {
  const visible = (photos || []).filter((p) => !p.is_deleted);
  if (visible.length === 0) return null;

  return (
    <div>
      {selectedPhotoId && (
        <p className="text-xs text-[color:var(--coral)] text-center mb-2 uppercase tracking-widest font-semibold">
          Click a spot on any page to place this photo
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2 justify-center" data-testid="photo-gallery">
        {visible.map((p) => {
          const placed = placedPhotoIds.has(p.id);
          const isSelected = selectedPhotoId === p.id;
          return (
            <div
              key={p.id}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData("text/photo-id", p.id);
                e.dataTransfer.effectAllowed = "copy";
              }}
              onClick={() => onSelectPhoto && onSelectPhoto(isSelected ? null : p.id)}
              data-testid={`gallery-photo-${p.id}`}
              title={isSelected ? "Click a page to place it — click here again to cancel" : "Click to place on a page, or drag it there"}
              className={`relative w-16 h-16 md:w-20 md:h-20 bg-white border overflow-hidden shrink-0 cursor-pointer active:cursor-grabbing transition-shadow ${
                isSelected ? "outline outline-2 outline-[color:var(--coral)] outline-offset-2" : "border-[color:var(--border-soft)]"
              }`}
            >
              <img
                src={photoImageUrl(p.id)}
                alt=""
                loading="lazy"
                className={`w-full h-full object-cover pointer-events-none select-none ${placed ? "opacity-50" : ""}`}
                draggable={false}
              />
              {placed && (
                <div className="absolute top-1 right-1 bg-[color:var(--ink)] text-[color:var(--paper)] rounded-full p-0.5">
                  <Check size={10} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
