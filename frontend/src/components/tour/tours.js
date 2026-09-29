// The steps of each guide: which element to highlight (CSS selector, or
// none for a centered message) and the key of its text in the locale files
// (tour.<guide>.<key>.title / .body).
import { TID } from "@/constants/testIds";

// Photos and page tools are on the inside pages: turn past the cover.
function openInsidePages() {
  if (document.querySelector('[data-tour="page-tools"]')?.getBoundingClientRect().width) return;
  document.querySelector(`[data-testid="${TID.editorNext}"]`)?.click();
}

export const EDITOR_TOUR = [
  { key: "welcome" },
  { key: "book", target: '[data-tour="book"]' },
  { key: "photo", target: '[data-tour="book"]', prepare: openInsidePages },
  { key: "pageTools", target: '[data-tour="page-tools"]', prepare: openInsidePages },
  { key: "pageNav", target: '[data-tour="page-nav"]' },
  { key: "pageCount", target: `[data-testid="${TID.editorChangePageCount}"]` },
  { key: "rearrange", target: '[data-tour="rearrange"]' },
  { key: "gallery", target: '[data-testid="photo-gallery"]' },
  { key: "addPhotos", target: '[data-tour="add-photos"]' },
  { key: "tools", target: '[data-tour="editor-tools"]' },
  { key: "order", target: `[data-testid="${TID.editorExportPdf}"]` },
  { key: "help", target: '[data-tour="tour-help"]' },
];

export const COVER_TOUR = [
  { key: "welcome", target: '[data-tour="cover-spread"]' },
  { key: "front", target: '[data-testid="cover-front"]' },
  { key: "spine", target: '[data-tour="cover-spine"]' },
  { key: "back", target: '[data-testid="cover-back"]' },
  { key: "panel", target: '[data-tour="cover-panel"]' },
  { key: "next", target: '[data-tour="wizard-continue"]' },
  { key: "help", target: '[data-tour="tour-help"]' },
];
