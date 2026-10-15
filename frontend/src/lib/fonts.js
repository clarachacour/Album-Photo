// Every font offered for a text (cover, spine, pages): one list, so each
// font picker offers the same ones. `kind` names the style next to it.
// The web fonts are loaded in index.html (the PDF is printed from the same
// pages, so it uses them too).
export const FONTS = [
  { value: "'Baloo 2', sans-serif", name: "Baloo", kind: "rounded" },
  { value: "'Manrope', sans-serif", name: "Manrope", kind: "sans" },
  { value: "'Cormorant Garamond', serif", name: "Cormorant", kind: "serif" },
  // Only its italic cut is loaded: the text shows in italic.
  { value: "'Playfair Display', serif", name: "Playfair", kind: "italic" },
  { value: "'Alex Brush', cursive", name: "Alex Brush", kind: "script" },
  { value: "Georgia, serif", name: "Georgia" },
  { value: "Helvetica, Arial, sans-serif", name: "Helvetica" },
  { value: "'Courier New', monospace", name: "Courier" },
];

export function fontName(value) {
  return FONTS.find((f) => f.value === value)?.name || String(value || "").split(",")[0].replace(/'/g, "");
}
