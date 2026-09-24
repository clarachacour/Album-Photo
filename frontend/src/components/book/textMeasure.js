// Same reference width the backend PDF export (backend/app/services/pdf.py) scales
// `title_font_size` / extra_items `font_size` against, so a value stored on
// a template renders at the same relative size here as it will in the final
// PDF. Kept as one named constant instead of the magic number 430 repeated
// inline, so the two stay easy to keep in sync.
export const REFERENCE_PAGE_PX = 430;

let _measureEl = null;
/**
 * Measures text width using an actual hidden DOM element instead of canvas.
 * Unlike canvas.measureText(), this automatically reflects letter-spacing,
 * text-transform, and whichever font actually ended up loaded — no manual
 * per-property correction needed, and no risk of measuring against a
 * fallback font before the real one is ready.
 */
export function measureDomTextWidth(text, { fontPx, fontWeight, fontFamily, letterSpacing, uppercase }) {
  if (typeof document === "undefined") return 0;
  if (!_measureEl) {
    _measureEl = document.createElement("span");
    _measureEl.style.position = "absolute";
    _measureEl.style.visibility = "hidden";
    _measureEl.style.whiteSpace = "pre";
    _measureEl.style.top = "-9999px";
    _measureEl.style.left = "-9999px";
    _measureEl.style.pointerEvents = "none";
    document.body.appendChild(_measureEl);
  }
  _measureEl.style.fontFamily = fontFamily;
  _measureEl.style.fontWeight = fontWeight || "400";
  _measureEl.style.fontSize = `${fontPx}px`;
  _measureEl.style.letterSpacing = letterSpacing || "normal";
  _measureEl.style.textTransform = uppercase ? "uppercase" : "none";
  _measureEl.textContent = text;
  return _measureEl.getBoundingClientRect().width;
}
