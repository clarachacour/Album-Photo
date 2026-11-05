// Print resolution of each photo, to warn when one risks coming out blurry
// (terms of sale, art. 5: the site points it out, the customer decides).
import { pageDimsMm } from "@/lib/printDims";
import { clampZoom, photoRect } from "@/lib/photoFit";

// The printer aims for 300 dpi; below 150 the loss of sharpness shows.
export const MIN_PRINT_DPI = 150;

/**
 * Pixels per inch of a photo once printed in its frame — the same sizing as
 * FramedPhoto (the photo covers the frame at zoom 1, bigger when zoomed in).
 * `item`: the frame on the page (x/y/w/h as fractions of the page, scale).
 * `photo`: its pixel size ({ width, height }). Null when unknown.
 */
export function photoPrintDpi(item, photo, size, orientation) {
  if (!photo?.width || !photo?.height || !item?.w || !item?.h) return null;
  const page = pageDimsMm(size, orientation);
  const frameWmm = item.w * page.w;
  const frameHmm = item.h * page.h;
  const frameAspect = frameWmm / frameHmm;
  const photoAspect = photo.width / photo.height;
  const rect = photoRect(frameAspect, photoAspect, clampZoom(item.scale ?? 1, frameAspect, photoAspect));
  const printedWidthInches = (rect.w * frameWmm) / 25.4;
  return photo.width / printedWidthInches;
}

export function isLowResolution(item, photo, size, orientation) {
  const dpi = photoPrintDpi(item, photo, size, orientation);
  return dpi !== null && dpi < MIN_PRINT_DPI;
}

/** Photo frames of the album that risk printing blurry. */
export function lowResolutionItems(album) {
  const photos = new Map((album?.photos || []).map((p) => [p.id, p]));
  const found = [];
  (album?.pages || []).forEach((page, pageIndex) => {
    for (const item of page.items || []) {
      if (item.type === "photo" && item.photo_id && isLowResolution(item, photos.get(item.photo_id), album.size, album.orientation)) {
        found.push({ pageIndex, item });
      }
    }
  });
  return found;
}

// Photos that risk printing dark: paper shows less light than a screen, so
// a dark photo comes out darker still. Measured at upload (brightness: mean
// lightness, 0-1). Calibrated on photos that did print too dark (evening
// restaurant photos, 0.17 and 0.22, flagged even with lamps and city lights
// in them) and ones that printed well (0.31 and up, a sunset included).
export const MIN_PRINT_BRIGHTNESS = 0.25;

export function isTooDark(photo) {
  return photo?.brightness != null && photo.brightness < MIN_PRINT_BRIGHTNESS;
}

/** Photo frames of the album whose photo risks printing dark. */
export function darkPhotoItems(album) {
  const photos = new Map((album?.photos || []).map((p) => [p.id, p]));
  const found = [];
  (album?.pages || []).forEach((page, pageIndex) => {
    for (const item of page.items || []) {
      if (item.type === "photo" && item.photo_id && isTooDark(photos.get(item.photo_id))) found.push({ pageIndex, item });
    }
  });
  return found;
}

// ---------- The cover ----------

/** A photo placed on the front or back cover (not a template's logo). */
export function isCoverPhotoItem(item) {
  return item?.type === "image" && (!!item.is_photo || (!!item.storage_path && !item.asset));
}

const coverSides = (album) => [
  ["front", album?.cover?.extra_items || []],
  ["back", album?.cover?.back_extra_items || []],
];

/**
 * The print warnings of a cover photo, as for the photos inside: blurry for
 * its frame, or dark. `measured`: its pixel size read in the browser, for a
 * photo placed before its size was kept on it (photo_width/photo_height).
 */
export function coverPhotoWarnings(item, size, orientation, measured) {
  if (!isCoverPhotoItem(item) || !item.image_url) return [];
  const photo = item.photo_width ? { width: item.photo_width, height: item.photo_height } : measured;
  return [
    isLowResolution(item, photo, size, orientation) && "lowResolution",
    isTooDark({ brightness: item.brightness }) && "tooDark",
  ].filter(Boolean);
}

/** The cover photos with a warning: [{ side, item, warnings }]. */
export function coverPhotoIssues(album, measuredSizes = {}) {
  const found = [];
  for (const [side, items] of coverSides(album)) {
    for (const item of items) {
      const warnings = coverPhotoWarnings(item, album.size, album.orientation, measuredSizes[item.id]);
      if (warnings.length) found.push({ side, item, warnings });
    }
  }
  return found;
}

/**
 * Photo frames left empty, inside and on the cover: not printed (the page
 * stays blank there), so the customer is told before ordering.
 * [{ pageIndex }] for the pages, [{ side }] for the cover.
 */
export function emptyFrames(album) {
  const found = [];
  (album?.pages || []).forEach((page, pageIndex) => {
    for (const item of page.items || []) {
      if (item.type === "photo" && !item.photo_id) found.push({ pageIndex });
    }
  });
  for (const [side, items] of coverSides(album)) {
    for (const item of items) {
      if (item.type === "image" && !item.image_url) found.push({ side });
    }
  }
  return found;
}
