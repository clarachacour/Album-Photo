import React, { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  MouseSensor,
  TouchSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { arrayMove, SortableContext, sortableKeyboardCoordinates, useSortable, rectSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { X } from "lucide-react";
import { AlbumPage } from "@/components/book/AlbumPage";

/** The order of `pages` once the page at `from` is dropped at `to`. */
export function movePage(pages, from, to) {
  if (from === to || from < 0 || to < 0 || from >= pages.length || to >= pages.length) return pages;
  return arrayMove(pages, from, to);
}

function PageCard({ page, index, orientation, size, sortable, onOpen, openLabel }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: `page-${index}`, disabled: !sortable });
  const style = { transform: CSS.Transform.toString(transform), transition, zIndex: isDragging ? 10 : undefined };
  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      // A click (not a drag: that needs a few pixels of movement, or a long
      // press on a phone) opens the page in the editor.
      onClick={() => onOpen(index)}
      title={openLabel}
      data-testid={`overview-page-${index}`}
      className={`relative select-none ${sortable ? "cursor-grab active:cursor-grabbing" : "cursor-pointer"} ${isDragging ? "opacity-60 scale-[1.03]" : ""}`}
    >
      <div className="bg-white shadow-sm border border-[color:var(--border-soft)] overflow-hidden pointer-events-none">
        <AlbumPage page={page} orientation={orientation} pageIndex={index} pageSize={size} imageVariant="thumb" />
      </div>
      <div className="mt-1.5 text-center text-[11px] text-[color:var(--muted)] tabular-nums">{index + 1}</div>
    </div>
  );
}

/**
 * Every page of the album at once, small: drag one to another place to
 * change the order (undoable like any edit), click one to open it in the
 * editor. Read-only (no dragging) once the album is ordered.
 */
export default function PageOverview({ album, editable, onReorder, onOpenPage, onClose }) {
  const { t } = useTranslation();
  const pages = album?.pages || [];
  const orientation = album?.orientation || "portrait";
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  // Escape closes; the page behind doesn't scroll meanwhile.
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
    };
  }, [onClose]);

  // The click that ends a drag isn't a click to open the page.
  const dragged = useRef(false);
  const open = (i) => {
    if (dragged.current) return;
    onOpenPage(i);
  };

  const handleDragEnd = ({ active, over }) => {
    setTimeout(() => { dragged.current = false; }, 80);
    if (!over || active.id === over.id) return;
    const from = parseInt(String(active.id).slice(5), 10);
    const to = parseInt(String(over.id).slice(5), 10);
    if (Number.isNaN(from) || Number.isNaN(to)) return;
    onReorder(movePage(pages, from, to), to);
  };

  const ids = pages.map((_, i) => `page-${i}`);
  const cols = orientation === "landscape" ? "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4" : "grid-cols-3 sm:grid-cols-4 lg:grid-cols-6";

  return (
    <div className="fixed inset-0 z-[60] bg-[color:var(--paper)] flex flex-col" role="dialog" aria-modal="true" aria-labelledby="page-overview-title" data-testid="page-overview">
      <div className="flex items-start justify-between gap-4 px-4 md:px-10 pt-6 pb-4 border-b border-[color:var(--border-soft)]">
        <div>
          <h2 id="page-overview-title" className="font-serif-display text-2xl md:text-3xl tracking-tight">{t("albumEditor.overview.title")}</h2>
          <p className="text-sm text-ink/70 mt-1">{t(editable ? "albumEditor.overview.hint" : "albumEditor.overview.hintReadOnly", { count: pages.length })}</p>
        </div>
        <button onClick={onClose} className="p-2 border border-ink/20 hover:bg-white shrink-0" aria-label={t("albumEditor.overview.close")} data-testid="page-overview-close">
          <X size={18} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 md:px-10 py-6">
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={() => { dragged.current = true; }} onDragEnd={handleDragEnd} onDragCancel={() => { dragged.current = false; }}>
          <SortableContext items={ids} strategy={rectSortingStrategy}>
            <div className={`grid ${cols} gap-x-4 gap-y-5 max-w-[1200px] mx-auto`}>
              {pages.map((page, i) => (
                <PageCard
                  key={page.id || `i-${i}`}
                  page={page}
                  index={i}
                  orientation={orientation}
                  size={album?.size}
                  sortable={editable}
                  onOpen={open}
                  openLabel={t("albumEditor.overview.open", { page: i + 1 })}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      </div>
    </div>
  );
}
