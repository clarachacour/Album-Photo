// Single default coffee-table cover — fully customizable by the user
// (background color, accent color, text color, logo image, optional cover photo, title/country/year).
//
// Colors and the logo below are sampled/extracted directly from the reference
// cover design, so the default rendering matches it exactly.
//
// NOTE on naming: the wizard (CreateAlbum.jsx) and the CoverMockup preview use
// `bg_color` / `accent_color` / `text_color` — the same field names stored on
// `album.cover` in the database. The in-editor renderer (AlbumPage.jsx) still
// expects a legacy `{ bg, accent, text, illustration }` shape for its *default*
// (pre-customization) palette, kept via DEFAULT_COVER_TEMPLATE below so we don't
// have to touch that renderer. Per-album overrides always use bg_color/accent_color/text_color.
import { CORAL_LOGO_DATA_URI } from "@/lib/coverAssets";

export const DEFAULT_TITLE_FONT = "'Baloo 2', sans-serif";

export const DEFAULT_COVER = {
  id: "default",
  name: "Classic",
  bg_color: "#009BB5",
  accent_color: "#F53769",
  text_color: "#63DDE0",
  title_font: DEFAULT_TITLE_FONT,
  title_font_weight: "800",
};

export const DEFAULT_COVER_TEMPLATE = {
  id: "default",
  name: "Classic",
  bg: DEFAULT_COVER.bg_color,
  accent: DEFAULT_COVER.accent_color,
  text: DEFAULT_COVER.text_color,
  illustration: null,
};

// The default logo/illustration shown on the front cover. It's a normal
// draggable "image" item on the cover (same system as text/shape extras),
// so the user can move it, resize it, delete it, or replace it with their own.
// The image itself is embedded as a base64 data URI (see coverAssets.js) —
// no file to place anywhere, it ships inside the code.
export function defaultLogoItem() {
  return {
    id: "default-logo",
    type: "image",
    x: 0.28,
    y: 0.42,
    w: 0.44,
    h: 0.4,
    image_url: CORAL_LOGO_DATA_URI,
    asset: "coral",
  };
}

// A small curated set of color presets to make customization quick.
// Users are never limited to these — the color pickers accept any color.
export const COVER_COLOR_PRESETS = [
  { id: "ocean-coral", name: "Ocean Coral", bg_color: "#009BB5", accent_color: "#F53769", text_color: "#63DDE0" },
  { id: "sand-forest", name: "Sand & Forest", bg_color: "#D5C9B3", accent_color: "#2C402E", text_color: "#1A1A17" },
  { id: "navy-blush", name: "Navy & Blush", bg_color: "#1C2D42", accent_color: "#E8D5D1", text_color: "#F9F8F6" },
  { id: "terracotta-cream", name: "Terracotta", bg_color: "#C05B3F", accent_color: "#F5EBDC", text_color: "#F9F8F6" },
  { id: "forest-gold", name: "Forest & Gold", bg_color: "#2C402E", accent_color: "#C9A959", text_color: "#F9F8F6" },
  { id: "charcoal-rose", name: "Charcoal & Rose", bg_color: "#2A2A28", accent_color: "#D89A9E", text_color: "#F9F8F6" },
];

// Backward-compatible helper: builds a full cover object (bg_color/accent_color/text_color)
// from whatever customization an album already has, falling back to the default palette.
export function getCover(cover) {
  return { ...DEFAULT_COVER, ...(cover || {}) };
}

// Legacy helper kept for the in-editor renderer (AlbumPage.jsx), which only needs
// the default palette shape — per-album customization is applied on top via its
// own `cover` prop, not through this function.
export function getTemplate() {
  return DEFAULT_COVER_TEMPLATE;
}