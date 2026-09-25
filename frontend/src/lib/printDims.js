// Physical page and spine dimensions, in millimeters — the single source of
// truth shared by the live editor (CreateAlbum.jsx, AlbumEditor.jsx) and the
// PDF export (PrintAlbum.jsx), so the spine width the person sees while
// editing always matches what actually gets printed. Previously each file
// either hardcoded a fixed 32px spine (editor) or its own copy of this same
// math (PrintAlbum.jsx) — a real book's spine should scale with the cover
// size and page count, not be a fixed pixel value.

// Physical page sizes in mm, matching the backend's reportlab A4/A5 tables.
// A3 removed — exceeded the printing office's max open hardcover size.
const PAGE_SIZES_MM = {
  A4: { w: 210, h: 297 },
  A5: { w: 148, h: 210 },
};

export function pageDimsMm(size, orientation) {
  const base = PAGE_SIZES_MM[(size || "A4").toUpperCase()] || PAGE_SIZES_MM.A4;
  return orientation === "landscape" ? { w: base.h, h: base.w } : { w: base.w, h: base.h };
}

// Spine thickness estimate from page count — thin album floors at 16mm,
// very thick ones cap at 35mm, so print stays physically sane either way.
export function spineWidthMm(numPages) {
  return Math.max(16, Math.min(35, 4 + (numPages || 0) * 0.12));
}

// Used before any photos are uploaded (e.g. the cover-editing step of the
// creation wizard, which comes before the "Pictures" step) — there's no
// real page count yet to base the spine on. 40 pages is a reasonable
// typical-album placeholder; AlbumEditor.jsx switches to the real
// album.pages.length as soon as it's known, same as the PDF export does.
export const DEFAULT_PAGE_COUNT_ESTIMATE = 40;

// The ratio to plug into a CSS grid-template-columns fraction (e.g.
// `1fr ${spineRatio(...)}fr 1fr`) or a percentage width, so the spine
// column's width is always proportional to the front cover's — instead of
// a fixed pixel value that shrinks to a tiny fraction on a wide cover and
// swallows the whole cover on a narrow one.
export function spineRatio(size, orientation, numPages) {
  const printer = printerCoverTemplate(size, orientation, numPages);
  if (printer) return printer.spine / printer.panelW;
  const { w: pageWidthMm } = pageDimsMm(size, orientation);
  return spineWidthMm(numPages) / pageWidthMm;
}

// Cover templates imposed by the printing office, in mm. Each one is a
// hardcover case laid flat on a single sheet, left to right:
//
//   wrap | back cover | hinge | spine | hinge | front cover | wrap
//
// with the same wrap above and below the covers, plus a bleed all around
// (trimmed off by the printer, so backgrounds must reach it). The covers'
// visible faces (panelW × panelH) keep the page's proportions, so the
// cover designs drop in unchanged, just scaled.
//
// Formats and page counts without a template here still get the older
// layout (spine + front on the first sheet, back cover on the last) —
// add each template as the printer sends it.
const PRINTER_COVER_TEMPLATES = [
  // Template_A4_1-50pgs.pdf: 475 × 330 mm trimmed.
  { size: "A4", orientation: "portrait", minPages: 1, maxPages: 50, bleed: 5, wrap: 20, panelW: 205, panelH: 290, hinge: 9, spine: 7 },
];

/** The printer's cover template for this album, or null when there is none yet. */
export function printerCoverTemplate(size, orientation, numPages) {
  const s = (size || "A4").toUpperCase();
  const o = orientation === "landscape" ? "landscape" : "portrait";
  const n = numPages || 0;
  return PRINTER_COVER_TEMPLATES.find((t) => t.size === s && t.orientation === o && n >= t.minPages && n <= t.maxPages) || null;
}

/**
 * Where everything goes on the cover sheet of a printer template, in mm from
 * the sheet's top-left corner (bleed included): the sheet itself, the
 * trimmed area, and the back cover, spine and front cover boxes.
 */
export function coverSpreadLayout(t) {
  const trimW = 2 * t.wrap + 2 * t.panelW + 2 * t.hinge + t.spine;
  const trimH = 2 * t.wrap + t.panelH;
  const top = t.bleed + t.wrap;
  const backX = t.bleed + t.wrap;
  const spineX = backX + t.panelW + t.hinge;
  const frontX = spineX + t.spine + t.hinge;
  return {
    sheet: { w: trimW + 2 * t.bleed, h: trimH + 2 * t.bleed },
    trim: { x: t.bleed, y: t.bleed, w: trimW, h: trimH },
    back: { x: backX, y: top, w: t.panelW, h: t.panelH },
    spine: { x: spineX, y: top, w: t.spine, h: t.panelH },
    front: { x: frontX, y: top, w: t.panelW, h: t.panelH },
  };
}
