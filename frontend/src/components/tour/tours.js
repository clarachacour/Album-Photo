// The steps of each guide: which element to highlight (CSS selector, or
// none for a centered message) and the key of its text in the locale files
// (tour.<guide>.<key>.title / .body). `prepare(context)` gets the page ready
// first — in the editor, `context` turns the book to the right page and
// selects a photo (see AlbumEditor).
import { TID } from "@/constants/testIds";

export const EDITOR_TOUR = [
  { key: "welcome", prepare: (ctx) => ctx.showCover() },
  { key: "book", target: '[data-tour="book"]', prepare: (ctx) => ctx.showCover() },
  { key: "firstPage", target: '[data-tour-page="0"]', prepare: (ctx) => ctx.showFirstPage() },
  { key: "photo", target: "[data-tour-selected]", prepare: (ctx) => ctx.showPhoto() },
  { key: "pageTools", target: '[data-tour="page-tools"]', prepare: (ctx) => ctx.showPhoto() },
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
