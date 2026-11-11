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
// Formats and page counts without a template here get the original layout
// (spine + front on the first sheet, back cover on the last).

// Template_A4_1-50pgs.pdf: 475 × 330 mm trimmed. Not in use: the owner went
// back to the original cover layout for every album. Put it back in the list
// below to use it again.
export const TEMPLATE_A4_1_50 = { size: "A4", orientation: "portrait", minPages: 1, maxPages: 50, bleed: 5, wrap: 20, panelW: 205, panelH: 290, hinge: 9, spine: 7 };

const PRINTER_COVER_TEMPLATES = [];

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
 * trimmed area, and the back cover, spine and front cover boxes. With
 * `marks` (mm), the sheet has that much more all around for the crop marks,
 * and `folds` gives where the boards, hinges and spine meet (for marks too).
 */
export function coverSpreadLayout(t) {
  const m = t.marks || 0;
  const trimW = 2 * t.wrap + 2 * t.panelW + 2 * t.hinge + t.spine;
  const trimH = 2 * t.wrap + t.panelH;
  const top = m + t.bleed + t.wrap;
  const backX = m + t.bleed + t.wrap;
  const spineX = backX + t.panelW + t.hinge;
  const frontX = spineX + t.spine + t.hinge;
  return {
    sheet: { w: trimW + 2 * (t.bleed + m), h: trimH + 2 * (t.bleed + m) },
    trim: { x: m + t.bleed, y: m + t.bleed, w: trimW, h: trimH },
    bleed: t.bleed,
    back: { x: backX, y: top, w: t.panelW, h: t.panelH },
    spine: { x: spineX, y: top, w: t.spine, h: t.panelH },
    front: { x: frontX, y: top, w: t.panelW, h: t.panelH },
    folds: {
      x: [backX, backX + t.panelW, spineX, spineX + t.spine, frontX, frontX + t.panelW],
      y: [top, top + t.panelH],
    },
  };
}

// ---------- The one-sheet hardcover format (Template_A4_1-50pgs) ----------
// The printer's file for a hardcover album, every format and page count:
// the cover on one sheet (TEMPLATE_A4_1_50's layout — wrap, hinges, boards
// a little smaller than the page — with the spine from the page count),
// then the pages, each with a bleed and crop marks, on white. Chosen in the
// admin (see backend services/print_format.py); the original layout stays
// for the other printer.

// The cover, from TEMPLATE_A4_1_50: board = page less 5 × 7 mm.
export const HARDCOVER = { bleed: 5, wrap: 20, hinge: 9, boardLessW: 5, boardLessH: 7, marks: 2.4 };

// A 170 g sheet is about 0.17 mm thick; the boards and the case add about
// 2.75 mm — which gives the template's 7 mm spine at 50 pages (25 sheets).
export const PAPER_SHEET_MM = 0.17;
const SPINE_CASE_MM = 2.75;

/** The spine width for this many pages, rounded up to the half millimetre (7 mm at least). */
export function hardcoverSpineMm(numPages) {
  const sheets = Math.ceil((numPages || 0) / 2);
  // Less a hair before rounding up: 15.5 computed as 15.500000001 stays 15.5.
  return Math.max(7, Math.ceil((SPINE_CASE_MM + sheets * PAPER_SHEET_MM) * 2 - 1e-9) / 2);
}

/** The cover sheet template for this album, in the one-sheet hardcover format. */
export function hardcoverCoverTemplate(size, orientation, numPages) {
  const page = pageDimsMm(size, orientation);
  return {
    bleed: HARDCOVER.bleed,
    wrap: HARDCOVER.wrap,
    hinge: HARDCOVER.hinge,
    marks: HARDCOVER.marks,
    panelW: page.w - HARDCOVER.boardLessW,
    panelH: page.h - HARDCOVER.boardLessH,
    spine: hardcoverSpineMm(numPages),
  };
}

// A page's bleed (what's beyond the cut, for photos touching an edge) and
// the room outside it for the crop marks, in mm.
export const PAGE_BLEED_MM = 3;
export const PAGE_MARKS_MM = 5;

/** A page's sheet in the one-sheet hardcover format: the page (trim) in the middle. */
export function pageSheetLayout(size, orientation) {
  const page = pageDimsMm(size, orientation);
  const edge = PAGE_BLEED_MM + PAGE_MARKS_MM;
  return {
    sheet: { w: page.w + 2 * edge, h: page.h + 2 * edge },
    trim: { x: edge, y: edge, w: page.w, h: page.h },
    bleed: PAGE_BLEED_MM,
  };
}

/**
 * A page's items for print with a bleed: a photo frame touching an edge of
 * the page goes `bleedMm` past it, so no white line shows if the cut is a
 * hair off. Other items stay as they are.
 */
export function withBleed(items, size, orientation, bleedMm) {
  const page = pageDimsMm(size, orientation);
  const bx = bleedMm / page.w;
  const by = bleedMm / page.h;
  const EDGE = 0.005; // within half a percent of the edge counts as touching it
  return (items || []).map((it) => {
    if (it.type !== "photo" || !it.photo_id || it.frame_rotation || it.w == null || it.h == null) return it;
    let { x = 0, y = 0, w, h } = it;
    if (x <= EDGE) { w += x + bx; x = -bx; }
    if (x + w >= 1 - EDGE) w = 1 + bx - x;
    if (y <= EDGE) { h += y + by; y = -by; }
    if (y + h >= 1 - EDGE) h = 1 + by - y;
    return x === it.x && y === it.y && w === it.w && h === it.h ? it : { ...it, x, y, w, h };
  });
}
