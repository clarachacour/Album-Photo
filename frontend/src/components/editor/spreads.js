// Converts a displayed "Double-page N" number (matching the flipbook's own
// "Double-page {pageIndex+1}" label) into how many entries of album.pages
// that actually corresponds to — NOT a simple divide-by-2, because the
// front cover is shown alone as its own spread first (see buildViews in
// Flipbook.jsx: [cover alone], [blank + page 0], [page 1 + page 2], [page 3
// + page 4], ...). Asking directly for a raw page-array count here was
// consistently off from what the person actually saw and meant.
export function spreadNumberToPageCount(spreadNumber) {
  if (spreadNumber <= 1) return 0;
  return Math.max(0, 2 * spreadNumber - 3);
}
