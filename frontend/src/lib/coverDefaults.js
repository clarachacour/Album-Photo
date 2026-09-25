// Where each cover element sits by default — what "Reset position" in the
// cover editor goes back to. One place for it, so the reset can never drift
// from where the element was actually placed in the first place.
import { findTemplate } from "@/lib/coverThemes";
import { defaultLogoItem } from "@/lib/coverTemplates";

// Front-cover title box when the album's template doesn't set one — the same
// fallback CoverFrontPage renders with.
export const DEFAULT_TITLE_BOX = { x: 0.08, y: 0.08, w: 0.84, h: 0.28 };

// Where an element appears when the person adds it from the editor.
export const NEW_ITEM_BOX = {
  text: { x: 0.1, y: 0.5, w: 0.5, h: 0.08 },
  shape: { x: 0.3, y: 0.6, w: 0.15, h: 0.15 },
  image: { x: 0.28, y: 0.42, w: 0.44, h: 0.4 },
};

const pickBox = (it) => ({ x: it.x, y: it.y, w: it.w, h: it.h });

function templateCover(album) {
  return findTemplate(album?.cover_template_id)?.cover || null;
}

export function defaultTitleBox(album) {
  const tpl = templateCover(album) || {};
  return {
    x: tpl.title_x ?? DEFAULT_TITLE_BOX.x,
    y: tpl.title_y ?? DEFAULT_TITLE_BOX.y,
    w: tpl.title_w ?? DEFAULT_TITLE_BOX.w,
    h: tpl.title_h ?? DEFAULT_TITLE_BOX.h,
  };
}

// Spine elements (prefix "spine_title", "spine_subtitle", "spine_caption"…):
// the template's own position, or null to let CoverSpine place it itself.
export function defaultSpineBox(album, prefix) {
  const tpl = templateCover(album) || {};
  return Object.fromEntries(["x", "y", "w", "h"].map((k) => [`${prefix}_${k}`, tpl[`${prefix}_${k}`] ?? null]));
}

// Elements of the same kind are matched in order (the 2nd photo frame of
// the album with the 2nd photo frame of its template).
const kindOf = (it) => [it.type, it.is_photo ? "photo" : "", it.shape_type || ""].join("|");

function templateItems(album, side) {
  const tpl = templateCover(album);
  if (side === "back") return tpl?.back_extra_items || [];
  // Albums created without a template start with the coral logo.
  return tpl?.extra_items || [defaultLogoItem()];
}

/**
 * Default box of a cover item: its place in the album's template if it came
 * from there, otherwise where it appeared when it was added.
 */
export function defaultItemBox(album, item, side = "front") {
  const tplItems = templateItems(album, side);
  const albumItems = (side === "back" ? album?.cover?.back_extra_items : album?.cover?.extra_items) || [];

  let match = null;
  if (item.template_item_id) {
    // Set on albums created since this was added: an exact link.
    match = tplItems.find((t) => t.id === item.template_item_id);
  } else if (item.asset) {
    match = tplItems.find((t) => t.asset === item.asset);
  } else if (item.role) {
    match = tplItems.find((t) => t.role === item.role);
  } else {
    const plain = (it) => !it.asset && !it.role && kindOf(it) === kindOf(item);
    const rank = albumItems.filter(plain).findIndex((it) => it.id === item.id);
    match = rank >= 0 ? tplItems.filter(plain)[rank] : null;
  }
  if (match) return pickBox(match);
  return { ...(NEW_ITEM_BOX[item.type] || NEW_ITEM_BOX.image) };
}
