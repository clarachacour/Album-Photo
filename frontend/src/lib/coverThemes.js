// Curated theme templates shown on the landing page and in the "choose a
// template" step of album creation. Each one seeds a fully editable cover —
// same system as the default template (drag/resize/recolor/retype anything)
// — starting from colors, fonts and decorative elements sampled from the
// reference designs, not a locked-in flat image.
import {
  TRAVEL_SICILY_ICON,
  TRAVEL_HAWAII_ICON,
  TRAVEL_THAILAND_ICON,
  TRAVEL_PAROS_ICON,
  TRAVEL_MOROCCO_ICON,
  TRAVEL_AUSTRALIA_ICON,
  TRAVEL_BARCELONA_ICON,
} from "@/lib/themeAssets";
import { CORAL_LOGO_URL } from "@/lib/coverAssets";

// Spine logos, files in public/cover-art (see coverAssets.js).
const RINGS_LOGO_URL = "/cover-art/rings-logo-v1.webp";
const HEART_LOGO_URL = "/cover-art/heart-logo-v1.webp";
const MOM_HEART_LOGO_URL = "/cover-art/mom-heart-logo-v1.webp";
const DAD_COMPASS_LOGO_URL = "/cover-art/dad-compass-logo-v1.webp";
const OURYEAR_RINGS_LOGO_URL = "/cover-art/ouryear-rings-logo-v1.webp";

// Spine logos were first shipped as small PNGs (58–103 px), blurry once
// enlarged or printed; the ones above are the same images upscaled 4x
// (Real-ESRGAN). Albums keep a copy of their template's logo in their
// cover, so the old copies are swapped for the new ones when shown.
const LEGACY_SPINE_LOGOS = [
  ["data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAGcAAABMCAYAAABwKqkMAABYGUlEQVR42k39e5RdZ3kmiD/ffe999rnU/aqqkqpkCSQQicDqxg", HEART_LOGO_URL],
  ["data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADoAAAA4CAYAAACsc+sjAAAf+UlEQVR42j276Y4cWZqe+ZzVNt9iZwS3JJNLbrV0t9SNqdbM/B", MOM_HEART_LOGO_URL],
  ["data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEwAAABLCAYAAADakmGTAAA3jklEQVR42lW8Z49lV5qd+Wxz/PXh00dGpCOTSSZdsYqsYjk5SE", DAD_COMPASS_LOGO_URL],
  ["data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEkAAAA6CAYAAAD8xXSzAAAg5UlEQVR42m2caZMjuXaenwMgFyb3YlX1NiNbEQ7JEf7/f0SydM", OURYEAR_RINGS_LOGO_URL],
  // Redrawn vector heart briefly used for Mom.
  ["data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%20100%20100%22%3E%3Cpath%20transform%3D%22rotate(84", MOM_HEART_LOGO_URL],
];

export function spineLogoSource(src) {
  if (typeof src !== "string") return src;
  const legacy = LEGACY_SPINE_LOGOS.find(([prefix]) => src.startsWith(prefix));
  return legacy ? legacy[1] : src;
}

const BALOO = "'Baloo 2', sans-serif";
const MANROPE = "'Manrope', sans-serif";
const CORMORANT = "'Cormorant Garamond', serif";
const SCRIPT = "'Alex Brush', cursive";

function iconItem(imageUrl, assetKey, box = { x: 0.28, y: 0.42, w: 0.44, h: 0.36 }) {
  return { id: "template-icon", type: "image", image_url: imageUrl, asset: assetKey, ...box };
}

let photoGridCounter = 0;
function photoGridItem(index, box) {
  photoGridCounter += 1;
  return { id: `photo-grid-${photoGridCounter}`, type: "image", is_photo: true, image_url: null, ...box };
}

function lineItem(box, color) {
  return { id: `line-${box.x}-${box.y}`, type: "shape", shape_type: "rect", fill_color: color, ...box };
}

function textItem(id, content, opts = {}) {
  return {
    id,
    type: "text",
    content,
    x: opts.x ?? 0.1,
    y: opts.y ?? 0.3,
    w: opts.w ?? 0.8,
    h: opts.h ?? 0.08,
    font: opts.font ?? MANROPE,
    font_weight: opts.font_weight ?? "700",
    font_size: opts.font_size ?? 20,
    color: opts.color,
    font_style: opts.font_style,
    text_align: opts.text_align,
    role: opts.role,
  };
}

export const COVER_THEMES = [
  {
    id: "travel",
    label: "Travel",
    templates: [
      {
        id: "travel-sicily",
        name: "Sicily",
        landingImage: "/theme-covers/travel-sicily.webp",
        title: "Sicily",
        cover: {
          bg_color: "#1B8F73",
          accent_color: "#E0C132",
          text_color: "#EAE7CE",
          title_font: BALOO,
          title_font_weight: "800",
          title_font_size: 66,
          title_x: 0.05, title_y: 0.04, title_w: 0.89, title_h: 0.18,
          spine_subtitle: "DOLCE",
          spine_subtitle_color: "#E0C132",
          spine_subtitle_font: BALOO,
          spine_subtitle_weight: "800",
          spine_title_size: 34,
          spine_title_font: BALOO,
          extra_items: [
            iconItem(TRAVEL_SICILY_ICON, "travel_sicily", { x: 0.306, y: 0.435, w: 0.388, h: 0.5 }),
            textItem("subtitle", "Dolce", { role: "subtitle", x: 0.44, y: 0.22, w: 0.5, h: 0.09, font: BALOO, font_weight: "800", font_size: 34, color: "#E0C132", text_align: "right" }),
          ],
        },
      },
      {
        id: "travel-hawaii",
        name: "Honolulu, Hawaii",
        landingImage: "/theme-covers/travel-hawaii.webp",
        title: "Honolulu",
        cover: {
          bg_color: "#D9ACA8",
          accent_color: "#D96A54",
          text_color: "#F3EFEC",
          title_font: BALOO,
          title_font_weight: "800",
          title_font_size: 66,
          title_x: 0.05, title_y: 0.04, title_w: 0.89, title_h: 0.18,
          spine_subtitle: "Hawaii",
          spine_subtitle_color: "#D96A54",
          spine_subtitle_font: BALOO,
          spine_subtitle_weight: "700",
          spine_title_size: 34,
          spine_title_font: BALOO,
          extra_items: [
            iconItem(TRAVEL_HAWAII_ICON, "travel_hawaii", { x: 0.16, y: 0.405, w: 0.72, h: 0.5 }),
            textItem("subtitle", "Hawaii", { role: "subtitle", x: 0.44, y: 0.22, w: 0.5, h: 0.08, font: BALOO, font_weight: "700", font_size: 28, color: "#D96A54", text_align: "right" }),
          ],
        },
      },
      {
        id: "travel-thailand",
        name: "Thailand",
        landingImage: "/theme-covers/travel-thailand.webp",
        title: "Thailand",
        cover: {
          bg_color: "#1B7A50",
          accent_color: "#C2A45E",
          text_color: "#F7F5EF",
          title_font: BALOO,
          title_font_weight: "800",
          title_font_size: 66,
          title_x: 0.05, title_y: 0.04, title_w: 0.89, title_h: 0.18,
          spine_subtitle: "Southeast Asia",
          spine_subtitle_color: "#C2A45E",
          spine_subtitle_font: BALOO,
          spine_subtitle_weight: "700",
          spine_title_size: 30,
          spine_title_font: BALOO,
          extra_items: [
            iconItem(TRAVEL_THAILAND_ICON, "travel_thailand", { x: 0.113, y: 0.415, w: 0.774, h: 0.5 }),
            textItem("subtitle", "Southeast Asia", { role: "subtitle", x: 0.34, y: 0.22, w: 0.6, h: 0.07, font: BALOO, font_weight: "700", font_size: 22, color: "#C2A45E", text_align: "right" }),
          ],
        },
      },
      {
        id: "travel-paros",
        name: "Paros, Greece",
        landingImage: "/theme-covers/travel-paros.webp",
        title: "Paros",
        cover: {
          bg_color: "#154A8C",
          accent_color: "#7EB6DB",
          text_color: "#F5F8FB",
          title_font: BALOO,
          title_font_weight: "800",
          title_font_size: 66,
          title_x: 0.05, title_y: 0.04, title_w: 0.89, title_h: 0.18,
          spine_subtitle: "Greece",
          spine_subtitle_color: "#7EB6DB",
          spine_subtitle_font: BALOO,
          spine_subtitle_weight: "700",
          spine_title_size: 34,
          spine_title_font: BALOO,
          extra_items: [
            iconItem(TRAVEL_PAROS_ICON, "travel_paros", { x: 0.151, y: 0.42, w: 0.698, h: 0.5 }),
            textItem("subtitle", "Greece", { role: "subtitle", x: 0.44, y: 0.22, w: 0.5, h: 0.08, font: BALOO, font_weight: "700", font_size: 28, color: "#7EB6DB", text_align: "right" }),
          ],
        },
      },
      {
        id: "travel-morocco",
        name: "Morocco, Africa",
        landingImage: "/theme-covers/travel-morocco.webp",
        title: "Morocco",
        cover: {
          bg_color: "#DCB987",
          accent_color: "#BE6B4D",
          text_color: "#FBF7F1",
          title_font: BALOO,
          title_font_weight: "800",
          title_font_size: 66,
          title_x: 0.05, title_y: 0.04, title_w: 0.89, title_h: 0.18,
          spine_subtitle: "Africa",
          spine_subtitle_color: "#BE6B4D",
          spine_subtitle_font: BALOO,
          spine_subtitle_weight: "700",
          spine_title_size: 32,
          spine_title_font: BALOO,
          extra_items: [
            iconItem(TRAVEL_MOROCCO_ICON, "travel_morocco", { x: 0.11, y: 0.403, w: 0.78, h: 0.444 }),
            textItem("subtitle", "Africa", { role: "subtitle", x: 0.44, y: 0.22, w: 0.5, h: 0.08, font: BALOO, font_weight: "700", font_size: 26, color: "#BE6B4D", text_align: "right" }),
          ],
        },
      },
      {
        id: "travel-australia",
        name: "Australia",
        landingImage: "/theme-covers/travel-australia.webp",
        title: "Australia",
        cover: {
          bg_color: "#166F8C",
          accent_color: "#F8625C",
          text_color: "#F3EBDD",
          title_font: BALOO,
          title_font_weight: "800",
          title_font_size: 66,
          title_x: 0.05, title_y: 0.04, title_w: 0.89, title_h: 0.18,
          spine_subtitle: "Adventure",
          spine_subtitle_color: "#F3EBDD",
          spine_subtitle_font: BALOO,
          spine_subtitle_weight: "700",
          spine_title_color: "#F8625C",
          spine_title_size: 30,
          spine_title_font: BALOO,
          extra_items: [
            iconItem(TRAVEL_AUSTRALIA_ICON, "travel_australia", { x: 0.11, y: 0.505, w: 0.78, h: 0.369 }),
            textItem("subtitle", "Adventure", { role: "subtitle", x: 0.29, y: 0.22, w: 0.65, h: 0.08, font: BALOO, font_weight: "700", font_size: 24, color: "#F3EBDD", text_align: "right" }),
          ],
        },
      },
      {
        id: "travel-barcelona",
        name: "Barcelona, Catalonia",
        landingImage: "/theme-covers/travel-barcelona.webp",
        title: "Barcelona",
        cover: {
          bg_color: "#B0C385",
          accent_color: "#D9764A",
          text_color: "#F5F3EA",
          title_font: BALOO,
          title_font_weight: "800",
          title_font_size: 66,
          title_x: 0.05, title_y: 0.04, title_w: 0.89, title_h: 0.18,
          spine_subtitle: "Catalonia",
          spine_subtitle_color: "#D9764A",
          spine_subtitle_font: BALOO,
          spine_subtitle_weight: "700",
          spine_title_size: 30,
          spine_title_font: BALOO,
          extra_items: [
            iconItem(TRAVEL_BARCELONA_ICON, "travel_barcelona", { x: 0.201, y: 0.44, w: 0.599, h: 0.5 }),
            textItem("subtitle", "Catalonia", { role: "subtitle", x: 0.34, y: 0.22, w: 0.6, h: 0.07, font: BALOO, font_weight: "700", font_size: 26, color: "#D9764A", text_align: "right" }),
          ],
        },
      },
    ],
  },
  {
    id: "couple",
    label: "Couple",
    templates: [
      {
        id: "couple-notre-rencontre",
        name: "Notre Rencontre",
        landingImage: "/theme-covers/couple-notre-rencontre.webp",
        title: "Notre Rencontre",
        cover: {
          bg_color: "#D3C0BA",
          accent_color: "#AD8973",
          text_color: "#AD8973",
          title_font: CORMORANT,
          title_font_weight: "700",
          title_writing_mode: "vertical-rl",
          title_uppercase: true,
          title_font_size: 30,
          title_x: 0.08, title_y: 0.06, title_w: 0.24, title_h: 0.88,
          spine_title_font: CORMORANT,
          spine_title_size: 28,
          spine_title_weight: "600",
          extra_items: [
            photoGridItem(0, { x: 0.4, y: 0.08, w: 0.54, h: 0.32 }),
            photoGridItem(1, { x: 0.4, y: 0.42, w: 0.26, h: 0.22 }),
            photoGridItem(2, { x: 0.68, y: 0.42, w: 0.26, h: 0.22 }),
            photoGridItem(3, { x: 0.4, y: 0.66, w: 0.54, h: 0.24 }),
          ],
        },
      },
      {
        id: "couple-notre-histoire",
        name: "Notre Histoire",
        landingImage: "/theme-covers/couple-notre-histoire.webp",
        title: "Notre histoire",
        cover: {
          bg_color: "#F8F6F2",
          accent_color: "#1A1A17",
          text_color: "#1A1A17",
          title_font: CORMORANT,
          title_font_weight: "600",
          title_single_line: true,
          title_text_align: "center",
          title_font_size: 34,
          title_x: 0.15, title_y: 0.06, title_w: 0.7, title_h: 0.14,
          spine_title_font: CORMORANT,
          spine_title_size: 28,
          spine_title_weight: "500",
          spine_logo_image: RINGS_LOGO_URL,
          spine_logo_x: 0.05, spine_logo_y: 0.84, spine_logo_w: 0.9, spine_logo_h: 0.12,
          extra_items: [
            photoGridItem(0, { x: 0.14, y: 0.36, w: 0.22, h: 0.42 }),
            photoGridItem(1, { x: 0.38, y: 0.3, w: 0.24, h: 0.5 }),
            photoGridItem(2, { x: 0.64, y: 0.36, w: 0.22, h: 0.42 }),
          ],
        },
      },
      {
        id: "couple-forever-journey",
        name: "Our Forever Journey",
        landingImage: "/theme-covers/couple-forever-journey.webp",
        title: "Our Forever Journey",
        cover: {
          bg_color: "#F5F5F3",
          accent_color: "#1A1A17",
          text_color: "#1A1A17",
          title_font: SCRIPT,
          title_font_weight: "400",
          title_single_line: true,
          title_uppercase: false,
          title_font_size: 40,
          title_x: 0.2, title_y: 0.08, title_w: 0.6, title_h: 0.1,
          spine_title_font: CORMORANT,
          spine_title_size: 24,
          spine_title_weight: "500",
          spine_title_y: 0.26,
          spine_caption: "CAMILLE & THOMAS\n15 MAY 2025",
          spine_caption_font: CORMORANT,
          spine_caption_size: 9,
          spine_caption_weight: "500",
          spine_caption_y: 0.75,
          extra_items: [
            // Asymmetric bracket around the photo, matching the reference:
            // the left line runs from the photo's top down to near the
            // page bottom; the right line runs from near the page top down
            // to the photo's bottom.
            lineItem({ x: 0.13, y: 0.28, w: 0.004, h: 0.64 }, "#1A1A17"),
            lineItem({ x: 0.85, y: 0.06, w: 0.004, h: 0.56 }, "#1A1A17"),
            photoGridItem(0, { x: 0.32, y: 0.28, w: 0.36, h: 0.34 }),
            textItem("date", "15 MAY 2025 - CAMILLE & THOMAS", { x: 0.13, y: 0.66, w: 0.74, h: 0.06, font: MANROPE, font_weight: "500", font_size: 13, color: "#1A1A17", text_align: "center" }),
          ],
        },
      },
    ],
  },
  {
    id: "family",
    label: "Family",
    templates: [
      {
        id: "family-plain",
        name: "family.",
        landingImage: "/theme-covers/family-plain.webp",
        title: "family.",
        cover: {
          bg_color: "#CEBAB4",
          accent_color: "#8A4A2B",
          text_color: "#8A4A2B",
          title_font: CORMORANT,
          title_font_weight: "800",
          title_uppercase: false,
          title_writing_mode: "vertical-rl",
          title_font_size: 90,
          title_x: 0.68, title_y: 0.46, title_w: 0.25, title_h: 0.5,
          spine_title_font: CORMORANT,
          spine_title_size: 24,
          spine_title_weight: "700",
          spine_title_y: 0.28,
          spine_title_text: "FAMILY",
          spine_title_color: "#B1977B",
          spine_logo_image: HEART_LOGO_URL,
          spine_logo_lines: true,
          spine_logo_x: 0.06, spine_logo_y: 0.46, spine_logo_w: 0.88, spine_logo_h: 0.16,
          spine_caption: "MEMORIES",
          spine_caption_font: CORMORANT,
          spine_caption_size: 22,
          spine_caption_weight: "600",
          spine_caption_color: "#B1977B",
          spine_caption_y: 0.64,
          extra_items: [],
        },
      },
      {
        id: "family-mom",
        name: "Mom",
        landingImage: "/theme-covers/family-mom.webp",
        title: "Mom",
        cover: {
          bg_color: "#B24862",
          accent_color: "#EFE6DD",
          text_color: "#EFE6DD",
          title_font: CORMORANT,
          title_font_weight: "700",
          title_uppercase: false,
          title_font_size: 40,
          title_x: 0.1, title_y: 0.33, title_w: 0.3, title_h: 0.14,
          title_fit_height: true,
          spine_title_font: CORMORANT,
          spine_title_size: 28,
          spine_title_weight: "600",
          spine_title_y: 0.18,
          spine_logo_image: MOM_HEART_LOGO_URL,
          spine_logo_lines: true,
          spine_logo_x: 0.06, spine_logo_y: 0.36, spine_logo_w: 0.88, spine_logo_h: 0.16,
          spine_caption: "MEMORIES",
          spine_caption_font: CORMORANT,
          spine_caption_size: 22,
          spine_caption_weight: "600",
          spine_caption_y: 0.52,
          extra_items: [
            textItem("definition", "Mom | noun", { x: 0.1, y: 0.5, w: 0.7, h: 0.06, font: CORMORANT, font_style: "italic", font_weight: "500", font_size: 16, color: "#EFE6DD" }),
            lineItem({ x: 0.1, y: 0.565, w: 0.55, h: 0.003 }, "#EFE6DD"),
            textItem("description", "The person who holds your hand, guides your heart, and fills your life with an unconditional love that shapes who you are.", { x: 0.1, y: 0.58, w: 0.75, h: 0.16, font: MANROPE, font_weight: "400", font_size: 12, color: "#EFE6DD" }),
            textItem("brand", "MEMORIES", { x: 0.35, y: 0.88, w: 0.3, h: 0.05, font: MANROPE, font_weight: "700", font_size: 11, color: "#EFE6DD", text_align: "center" }),
          ],
        },
      },
      {
        id: "family-dad",
        name: "Dad",
        landingImage: "/theme-covers/family-dad.webp",
        title: "Dad",
        cover: {
          bg_color: "#26354B",
          accent_color: "#D9C6A3",
          text_color: "#D9C6A3",
          title_font: CORMORANT,
          title_font_weight: "700",
          title_uppercase: false,
          title_font_size: 40,
          title_x: 0.1, title_y: 0.33, title_w: 0.3, title_h: 0.14,
          title_fit_height: true,
          spine_title_font: CORMORANT,
          spine_title_size: 28,
          spine_title_weight: "600",
          spine_title_y: 0.18,
          spine_logo_image: DAD_COMPASS_LOGO_URL,
          spine_logo_lines: true,
          spine_logo_x: 0.06, spine_logo_y: 0.36, spine_logo_w: 0.88, spine_logo_h: 0.16,
          spine_caption: "MEMORIES",
          spine_caption_font: CORMORANT,
          spine_caption_size: 22,
          spine_caption_weight: "600",
          spine_caption_y: 0.52,
          extra_items: [
            textItem("definition", "Dad | noun", { x: 0.1, y: 0.5, w: 0.7, h: 0.06, font: CORMORANT, font_style: "italic", font_weight: "500", font_size: 16, color: "#D9C6A3" }),
            lineItem({ x: 0.1, y: 0.565, w: 0.55, h: 0.003 }, "#D9C6A3"),
            textItem("description", "The person who holds your hand, guides your heart, and fills your life with strength, wisdom, and an unwavering presence.", { x: 0.1, y: 0.58, w: 0.75, h: 0.16, font: MANROPE, font_weight: "400", font_size: 12, color: "#D9C6A3" }),
            textItem("brand", "MEMORIES", { x: 0.35, y: 0.88, w: 0.3, h: 0.05, font: MANROPE, font_weight: "700", font_size: 11, color: "#D9C6A3", text_align: "center" }),
          ],
        },
      },
    ],
  },
  {
    id: "celebrations",
    label: "Celebrations",
    templates: [
      {
        id: "celebrations-best-friends",
        name: "Best Friends",
        landingImage: "/theme-covers/celebrations-best-friends.webp",
        title: "Best friends",
        cover: {
          bg_color: "#3C5065",
          accent_color: "#E8E3D8",
          text_color: "#E8E3D8",
          title_font: CORMORANT,
          title_font_weight: "700",
          title_uppercase: false,
          title_single_line: true,
          title_font_size: 40,
          title_x: 0.1, title_y: 0.33, title_w: 0.55, title_h: 0.14,
          spine_title_font: CORMORANT,
          spine_title_size: 28,
          spine_title_weight: "600",
          spine_title_text: "BEST FRIENDS",
          spine_title_y: 0.25,
          spine_title_caption_divider: true,
          spine_caption: "MEMORIES",
          spine_caption_font: CORMORANT,
          spine_caption_size: 22,
          spine_caption_weight: "600",
          spine_caption_y: 0.47,
          extra_items: [
            textItem("definition", "Best friends | noun", { x: 0.1, y: 0.5, w: 0.75, h: 0.06, font: CORMORANT, font_style: "italic", font_weight: "500", font_size: 16, color: "#E8E3D8" }),
            lineItem({ x: 0.1, y: 0.565, w: 0.55, h: 0.003 }, "#E8E3D8"),
            textItem("description", "The person who turns everyday moments into memories, the one who fills the pages of your life with laughter, tears, and stories you'll always treasure.", { x: 0.1, y: 0.58, w: 0.78, h: 0.18, font: CORMORANT, font_weight: "400", font_size: 14, color: "#E8E3D8" }),
            textItem("brand", "MEMORIES", { x: 0.35, y: 0.9, w: 0.3, h: 0.05, font: MANROPE, font_weight: "700", font_size: 11, color: "#E8E3D8", text_align: "center" }),
          ],
        },
        placeholder: true, // more Celebrations templates coming later
      },
      {
        id: "celebrations-our-year",
        name: "Our Year",
        landingImage: "/theme-covers/celebrations-our-year.webp",
        title: "Our Year",
        cover: {
          bg_color: "#E6DBD7",
          accent_color: "#8A5C2F",
          text_color: "#8A5C2F",
          title_font: CORMORANT,
          title_font_weight: "700",
          title_writing_mode: "vertical-rl",
          title_uppercase: true,
          title_font_size: 34,
          title_x: 0.08, title_y: 0.1, title_w: 0.24, title_h: 0.8,
          spine_title_font: CORMORANT,
          spine_title_size: 28,
          spine_title_weight: "600",
          spine_title_y: 0.32,
          spine_logo_image: OURYEAR_RINGS_LOGO_URL,
          spine_logo_x: 0.12, spine_logo_y: 0.86, spine_logo_w: 0.76, spine_logo_h: 0.1,
          extra_items: [
            photoGridItem(0, { x: 0.4, y: 0.08, w: 0.28, h: 0.24 }),
            photoGridItem(1, { x: 0.7, y: 0.08, w: 0.24, h: 0.24 }),
            photoGridItem(2, { x: 0.4, y: 0.34, w: 0.24, h: 0.24 }),
            photoGridItem(3, { x: 0.66, y: 0.34, w: 0.28, h: 0.24 }),
            photoGridItem(4, { x: 0.4, y: 0.6, w: 0.54, h: 0.26 }),
          ],
        },
      },
    ],
  },
];

export function findTemplate(templateId) {
  for (const theme of COVER_THEMES) {
    const found = theme.templates.find((t) => t.id === templateId);
    if (found) return found;
  }
  return null;
}
