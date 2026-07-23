import React from "react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  horizontalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { photoImageUrl } from "@/lib/api";

function SortablePhoto({ id, index }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: `slot-${index}` });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };
  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      data-testid={`tray-photo-${index}`}
      className="relative w-20 h-20 md:w-24 md:h-24 bg-white cursor-grab active:cursor-grabbing border border-[color:var(--border-soft)] overflow-hidden shrink-0 group"
    >
      <img src={photoImageUrl(id)} alt="" className="w-full h-full object-cover pointer-events-none" draggable={false} />
      <div className="absolute bottom-1 left-1 bg-[color:var(--ink)] text-[color:var(--paper)] text-[9px] px-1.5 py-0.5 font-sans font-semibold">
        {index + 1}
      </div>
    </div>
  );
}

export default function PhotoTray({ photoIds, onReorder }) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const handleDragEnd = (event) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const activeIdx = parseInt(String(active.id).replace("slot-", ""), 10);
    const overIdx = parseInt(String(over.id).replace("slot-", ""), 10);
    if (Number.isNaN(activeIdx) || Number.isNaN(overIdx)) return;
    const newOrder = arrayMove(photoIds, activeIdx, overIdx);
    onReorder(newOrder);
  };

  if (!photoIds || photoIds.length === 0) return null;

  const items = photoIds.map((_, i) => `slot-${i}`);

  return (
    <div className="bg-white border border-[color:var(--border-soft)] p-4">
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={items} strategy={horizontalListSortingStrategy}>
          <div className="flex gap-2 overflow-x-auto pb-2" data-testid="photo-tray">
            {photoIds.map((photoId, idx) => (
              <SortablePhoto key={`${photoId}-${idx}`} id={photoId} index={idx} />
            ))}
          </div>
        </SortableContext>
      </DndContext>
    </div>
  );
}
