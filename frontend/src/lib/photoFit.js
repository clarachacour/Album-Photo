// Geometry of a photo inside its frame. Positions are fractions of the page
// (0-1), so a frame's real aspect ratio is (w / h) * PAGE_ASPECT_WH.
// Mirrors fit_box_to_photo in backend/app/services/layout.py.

// A4 / A5 share the ISO 216 ratio: only the orientation matters.
export const PAGE_ASPECT_WH = { portrait: 0.7071, landscape: 1.4142 };
export const MAX_ZOOM = 2.5;

export function pageAspect(orientation) {
  return PAGE_ASPECT_WH[orientation] || PAGE_ASPECT_WH.portrait;
}

export function photoAspectOf(photo) {
  return photo?.width && photo?.height ? photo.width / photo.height : null;
}

/** Largest box with the photo's proportions inside `slot`, centered in it. */
export function fitBoxToAspect(slot, photoAspect, orientation) {
  const box = { x: slot.x, y: slot.y, w: slot.w, h: slot.h };
  if (!photoAspect || photoAspect <= 0) return box;
  const pa = pageAspect(orientation);
  const slotAspect = (slot.w / slot.h) * pa;
  if (photoAspect >= slotAspect) {
    box.h = (slot.w * pa) / photoAspect;
  } else {
    box.w = (slot.h * photoAspect) / pa;
  }
  box.x = slot.x + (slot.w - box.w) / 2;
  box.y = slot.y + (slot.h - box.h) / 2;
  return box;
}

/**
 * Size of the photo relative to its frame when it just covers it (zoom 1),
 * e.g. { w: 1.33, h: 1 } for a landscape photo in a square frame.
 */
export function coverSize(frameAspect, photoAspect) {
  return photoAspect >= frameAspect
    ? { w: photoAspect / frameAspect, h: 1 }
    : { w: 1, h: frameAspect / photoAspect };
}

/** Zoom at which the whole photo is visible in the frame (≤ 1). */
export function minZoom(frameAspect, photoAspect) {
  if (!frameAspect || !photoAspect) return 1;
  const c = coverSize(frameAspect, photoAspect);
  return 1 / Math.max(c.w, c.h);
}

export function clampZoom(zoom, frameAspect, photoAspect) {
  const z = Number.isFinite(zoom) ? zoom : 1;
  return Math.min(MAX_ZOOM, Math.max(minZoom(frameAspect, photoAspect), z));
}

/**
 * Where the photo sits in its frame, as fractions of the frame: at zoom 1 it
 * covers the frame, below 1 it shrinks until fully visible. The focal point
 * decides which part stays in view (same rule as CSS object-position).
 */
export function photoRect(frameAspect, photoAspect, zoom, focalX = 0.5, focalY = 0.5) {
  const c = coverSize(frameAspect, photoAspect);
  const w = c.w * zoom;
  const h = c.h * zoom;
  return { w, h, left: (1 - w) * focalX, top: (1 - h) * focalY };
}

/**
 * New position fields for a frame receiving `photo` (swap, replace, layout
 * change…): the frame takes the photo's proportions inside its slot — the
 * area it was given by the layout — so the photo is never cropped. Keeping
 * the slot means repeated swaps don't shrink the frame step by step.
 */
export function fitItemToPhoto(item, photo, orientation) {
  const slot = item.slot || { x: item.x, y: item.y, w: item.w, h: item.h };
  const aspect = photoAspectOf(photo);
  if (!aspect) return { ...slot, slot, photo_aspect: null };
  return { ...fitBoxToAspect(slot, aspect, orientation), slot, photo_aspect: aspect };
}
