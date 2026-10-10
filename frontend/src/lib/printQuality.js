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
// an underexposed photo comes out darker still. Measured at upload
// (brightness: mean lightness, highlights: that of the brightest tenth, 0-1).
// A sunset or a night shot with lights keeps bright highlights: not flagged.
export function isTooDark(photo) {
  if (photo?.brightness == null) return false;
  return photo.brightness < 0.12 || (photo.brightness < 0.22 && (photo.highlights ?? 1) < 0.45);
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
