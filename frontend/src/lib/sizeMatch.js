/**
 * "Size magnet" for photo frames: while a frame is being resized, a width
 * or height close to another frame's — on the same page or the facing page
 * of the spread — snaps to it exactly, and both frames are marked, so two
 * photos can be given exactly the same format.
 *
 * Sizes are fractions of the page (item.w, item.h); both pages of a spread
 * are the same size, so frames on facing pages compare directly.
 */

// How close (fraction of the page) counts as "the same": ~3 mm on A4.
export const SIZE_SNAP = 0.015;
const SAME = 0.0005;

/**
 * The album page facing page `index` in its spread. The flipbook shows the
 * front cover alone, then (blank, page 0), (page 1, page 2), (page 3, page
 * 4)…: an even page is on the right, its facing page is the one before.
 */
export function facingPageIndex(index, pageCount) {
  const other = index % 2 === 0 ? index - 1 : index + 1;
  return other >= 0 && other < pageCount ? other : null;
}

/** The other photo frames of the spread: [{ id, w, h, pageIndex }]. */
export function spreadPhotoFrames(pages, pageIndex, itemId) {
  const frames = [];
  for (const i of [pageIndex, facingPageIndex(pageIndex, pages.length)]) {
    if (i === null || !pages[i]) continue;
    for (const it of pages[i].items || []) {
      if (it.type === "photo" && it.id !== itemId && it.w != null && it.h != null) {
        frames.push({ id: it.id, w: it.w, h: it.h, pageIndex: i });
      }
    }
  }
  return frames;
}

function closest(value, frames, key, max) {
  let best = null;
  for (const f of frames) {
    if (f[key] > max + 1e-9) continue; // that size would go past the page edge
    const diff = Math.abs(value - f[key]);
    if (diff < SIZE_SNAP && (!best || diff < best.diff)) best = { diff, value: f[key] };
  }
  return best ? best.value : null;
}

/**
 * The size to use while resizing to (w, h): each of the two snapped to the
 * closest other frame's within SIZE_SNAP. Returns
 * { w, h, snappedW, snappedH, matches: [{ id, pageIndex, kind }] } where
 * kind is "both", "w" or "h" — the frames that now share the size.
 * maxW / maxH: the room left before the page edge (no snapping past it).
 */
export function snapToSameSize(w, h, frames, { maxW = 1, maxH = 1 } = {}) {
  const sw = closest(w, frames, "w", maxW);
  const sh = closest(h, frames, "h", maxH);
  const nw = sw ?? w;
  const nh = sh ?? h;
  const matches = [];
  for (const f of frames) {
    const sameW = Math.abs(f.w - nw) < SAME;
    const sameH = Math.abs(f.h - nh) < SAME;
    if (sameW || sameH) matches.push({ id: f.id, pageIndex: f.pageIndex, kind: sameW && sameH ? "both" : sameW ? "w" : "h" });
  }
  return { w: nw, h: nh, snappedW: sw !== null, snappedH: sh !== null, matches };
}
