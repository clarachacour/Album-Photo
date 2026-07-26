import React from "react";
import { photoImageUrl } from "@/lib/api";
import { Check } from "lucide-react";

/**
 * Shows every photo uploaded to the album — including the ones the AI didn't
 * pick for the layout — so the user can drag a missing one straight onto a
 * page. Placed photos are marked with a check; dragging works the same for
 * both (drop on an empty frame to add it, on a filled frame to replace it).
 */
export default function PhotoGallery({ photos, placedPhotoIds }) {
  const visible = (photos || []).filter((p) => !p.is_deleted);
  if (visible.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-2 justify-center" data-testid="photo-gallery">
      {visible.map((p) => {
        const placed = placedPhotoIds.has(p.id);
        return (
          <div
            key={p.id}
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData("text/photo-id", p.id);
              e.dataTransfer.effectAllowed = "copy";
            }}
            data-testid={`gallery-photo-${p.id}`}
            title={placed ? "Déjà utilisée — glissez pour la dupliquer ailleurs" : "Glissez sur une page pour l'ajouter"}
            className="relative w-16 h-16 md:w-20 md:h-20 bg-white border border-[color:var(--border-soft)] overflow-hidden shrink-0 cursor-grab active:cursor-grabbing"
          >
            <img
              src={photoImageUrl(p.id)}
              alt=""
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
  );
}