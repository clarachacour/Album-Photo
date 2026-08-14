// Physical page and spine dimensions, in millimeters — the single source of
// truth shared by the live editor (CreateAlbum.jsx, AlbumEditor.jsx) and the
// PDF export (PrintAlbum.jsx), so the spine width the person sees while
// editing always matches what actually gets printed. Previously each file
// either hardcoded a fixed 32px spine (editor) or its own copy of this same
// math (PrintAlbum.jsx) — a real book's spine should scale with the cover
// size and page count, not be a fixed pixel value.

// Physical page sizes in mm, matching the backend's reportlab A3/A4/A5 tables.
const PAGE_SIZES_MM = {
  A3: { w: 297, h: 420 },
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
  const { w: pageWidthMm } = pageDimsMm(size, orientation);
  return spineWidthMm(numPages) / pageWidthMm;
}
