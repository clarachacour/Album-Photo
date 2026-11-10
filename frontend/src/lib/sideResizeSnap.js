import { snapEdge } from "@/lib/coverEditing";
import { snapToSameSize } from "@/lib/sizeMatch";

const MOVED = 1e-6;
const MIN_SIZE = 0.02;

/** Which edge of one axis a resize moved: "start", "end" or null. */
function movedEdge(start0, size0, start1, size1) {
  const startMoved = Math.abs(start1 - start0) > MOVED;
  const endMoved = Math.abs(start1 + size1 - (start0 + size0)) > MOVED;
  if (startMoved && !endMoved) return "start";
  if (endMoved && !startMoved) return "end";
  return null;
}

/**
 * A frame resized from one of its sides or corners ({ x, y, w, h } patch):
 * the same help as from the bottom-right corner. A photo frame's width or
 * height close to another photo frame's on the spread takes it (`frames`,
 * see sizeMatch); otherwise the pulled edge lines up with the page centre or
 * another item's edge or centre, with a guide line. The side that wasn't
 * pulled never moves. Returns { patch, guideX, guideY, matches }.
 */
export function snapSideResize(item, patch, siblings, frames = null) {
  const out = { ...patch };
  const moved = {
    x: movedEdge(item.x ?? 0, item.w ?? 0, patch.x, patch.w),
    y: movedEdge(item.y ?? 0, item.h ?? 0, patch.y, patch.h),
  };
  const end = { x: (item.x ?? 0) + (item.w ?? 0), y: (item.y ?? 0) + (item.h ?? 0) };
  const locked = { x: false, y: false };
  let matches = [];

  if (frames) {
    const room = (axis, size) => (moved[axis] === "start" ? end[axis] : 1 - (item[axis] ?? 0)) || item[size];
    const s = snapToSameSize(patch.w, patch.h, frames, { maxW: room("x", "w"), maxH: room("y", "h") });
    for (const [axis, size, snapped] of [["x", "w", s.snappedW], ["y", "h", s.snappedH]]) {
      if (!snapped || !moved[axis]) continue;
      out[size] = s[size];
      out[axis] = moved[axis] === "start" ? end[axis] - s[size] : item[axis] ?? 0;
      locked[axis] = true;
    }
    if (locked.x || locked.y) matches = s.matches;
  }

  const guides = { x: null, y: null };
  for (const [axis, size] of [["x", "w"], ["y", "h"]]) {
    if (!moved[axis]) continue;
    const edge = moved[axis] === "start" ? out[axis] : out[axis] + out[size];
    const s = snapEdge(edge, siblings, axis);
    if (s.guide === null) continue;
    if (locked[axis]) {
      // Same size as another photo: the guide line still shows when the
      // pulled edge also lines up with something (it isn't moved for it).
      if (Math.abs(s.value - edge) < 1e-6) guides[axis] = s.guide;
      continue;
    }
    if (moved[axis] === "start") {
      if (end[axis] - s.value < MIN_SIZE) continue;
      out[axis] = s.value;
      out[size] = end[axis] - s.value;
    } else {
      if (s.value - out[axis] < MIN_SIZE) continue;
      out[size] = s.value - out[axis];
    }
    guides[axis] = s.guide;
  }
  return { patch: out, guideX: guides.x, guideY: guides.y, matches };
}
