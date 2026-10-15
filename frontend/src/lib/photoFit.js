// Geometry of a photo inside its frame. Positions are fractions of the page
// (0-1), so a frame's real aspect ratio is (w / h) * PAGE_ASPECT_WH.
// Mirrors fit_box_to_photo in backend/app/services/layout.py.

import { MAX_CROP } from "@/lib/layoutPatterns";

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

// A face's centre must stay at least this far (fraction of the photo) from
// an edge the frame cuts. Mirrors FACE_MARGIN in the backend's layout.py.
const FACE_MARGIN = 0.12;

/** Fraction of the photo a frame of frameAspect cuts off (0 = shown whole). */
export function cutFraction(frameAspect, photoAspect) {
  if (!frameAspect || !photoAspect) return 0;
  return 1 - Math.min(frameAspect / photoAspect, photoAspect / frameAspect);
}

function faceSafe(photo, photoAspect, frameAspect) {
  if (!photo?.ai_has_face) return true;
  const wider = photoAspect >= frameAspect; // cut left/right, else top/bottom
  const kept = wider ? frameAspect / photoAspect : photoAspect / frameAspect;
  const focal = (wider ? photo.ai_focal_x : photo.ai_focal_y) ?? 0.5;
  const start = focal * (1 - kept); // where the visible part starts (CSS object-position)
  return focal - start >= FACE_MARGIN && start + kept - focal >= FACE_MARGIN;
}

/**
 * The frame for `photo` in `slot` — same rule as frame_for in the backend:
 * the whole slot when filling it cuts at most MAX_CROP of the photo and
 * never into a detected face (frames then line up exactly with the
 * template), otherwise the photo's own shape inside the slot.
 */
export function frameForPhoto(slot, photo, orientation) {
  const box = { x: slot.x, y: slot.y, w: slot.w, h: slot.h };
  const aspect = photoAspectOf(photo);
  if (!aspect) return box;
  const slotAspect = (slot.w / slot.h) * pageAspect(orientation);
  if (cutFraction(slotAspect, aspect) <= MAX_CROP + 1e-9 && faceSafe(photo, aspect, slotAspect)) return box;
  return fitBoxToAspect(slot, aspect, orientation);
}

/**
 * New position fields for a frame receiving `photo` (swap, replace, layout
 * change…), placed in its slot — the area it was given by the layout — by
 * frameForPhoto. Keeping the slot means repeated swaps don't shrink the
 * frame step by step.
 */
export function fitItemToPhoto(item, photo, orientation) {
  const slot = item.slot || { x: item.x, y: item.y, w: item.w, h: item.h };
  const aspect = photoAspectOf(photo);
  if (!aspect) return { ...slot, slot, photo_aspect: null };
  return { ...frameForPhoto(slot, photo, orientation), slot, photo_aspect: aspect };
}

/** "Show the whole photo": the frame takes the photo's own shape in its slot, nothing cut. */
export function wholePhotoFields(item, photo, orientation) {
  const slot = item.slot || { x: item.x, y: item.y, w: item.w, h: item.h };
  const aspect = photoAspectOf(photo) || item.photo_aspect;
  if (!aspect) return {};
  return { ...fitBoxToAspect(slot, aspect, orientation), slot, photo_aspect: aspect, scale: 1 };
}

/** Whether a frame currently hides part of its photo (beyond rounding). */
export function isCropped(item, photo, orientation) {
  const aspect = photoAspectOf(photo) || item.photo_aspect;
  if (!aspect || !item.w || !item.h) return false;
  return cutFraction((item.w / item.h) * pageAspect(orientation), aspect) > 0.005;
}

/**
 * The zoom a photo turned by `degrees` inside its frame needs so the frame
 * stays filled (no empty corners): the frame's box must fit inside the
 * turned photo, which at zoom 1 just covers the frame.
 */
export function zoomToFillTurned(frameAspect, degrees) {
  const a = (Math.abs(degrees || 0) % 180) * (Math.PI / 180);
  const cos = Math.abs(Math.cos(a));
  const sin = Math.abs(Math.sin(a));
  const fa = frameAspect || 1;
  return cos + Math.max(fa, 1 / fa) * sin;
}

/**
 * A photo frame resized from a side or corner crops its photo: the photo
 * stays where it is on the page (same size, same place) and only the frame's
 * edge moves over it. Adds the zoom and focal point that keep it there to
 * `patch` (new x/y/w/h). Pulled past the photo's edge, the photo grows to
 * keep the frame filled. A photo turned in its frame keeps the old way.
 */
export function cropPatch(item, patch, orientation, photoAspect) {
  if (!photoAspect || item.rotation || (patch.w === undefined && patch.h === undefined)) return patch;
  const pa = pageAspect(orientation);
  const n = { x: item.x, y: item.y, w: item.w, h: item.h, ...patch };
  // Frame sizes in one unit (page height = 1).
  const fw = item.w * pa, fh = item.h;
  const nw = n.w * pa, nh = n.h;
  if (!(fw > 0 && fh > 0 && nw > 0 && nh > 0)) return patch;
  // How far the frame's own top-left corner moved, along its own sides.
  const a = (-(item.frame_rotation || 0) * Math.PI) / 180;
  const dcx = (n.x + n.w / 2 - (item.x + item.w / 2)) * pa;
  const dcy = n.y + n.h / 2 - (item.y + item.h / 2);
  const ox = dcx * Math.cos(a) - dcy * Math.sin(a) - (nw - fw) / 2;
  const oy = dcx * Math.sin(a) + dcy * Math.cos(a) - (nh - fh) / 2;
  // The photo now, in the frame.
  const zoom = item.scale ?? 1;
  const c = coverSize(fw / fh, photoAspect);
  const iw = c.w * zoom * fw, ih = c.h * zoom * fh;
  const left = (fw - iw) * (item.focal_x ?? 0.5) - ox;
  const top = (fh - ih) * (item.focal_y ?? 0.5) - oy;
  // Same size in the new frame (never smaller than filling it, unless it
  // was already shown smaller).
  const nc = coverSize(nw / nh, photoAspect);
  const nz = Math.min(MAX_ZOOM, Math.max(Math.min(1, zoom), iw / (nc.w * nw)));
  const niw = nc.w * nz * nw, nih = nc.h * nz * nh;
  const focal = (offset, frame, img) => (Math.abs(frame - img) < 1e-9 ? 0.5 : Math.min(1, Math.max(0, offset / (frame - img))));
  return { ...patch, scale: nz, focal_x: focal(left, nw, niw), focal_y: focal(top, nh, nih) };
}
