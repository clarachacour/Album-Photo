// The generic texts the site puts in an album for the person to replace
// ("This is your first page…", "Your caption", "New text"…). If they're
// still there as is when the album is printed, they're left out of the PDF
// (see PrintAlbum.jsx): the customer forgot them, the book shouldn't show
// them. The editor still shows them, to be changed or deleted.
//
// In English and French, as written by backend/app/services/layout.py
// (make_title_page) and the locale files (albumEditor.yourCaption,
// coverPanel.newText, coverPanel.yourText) — placeholderText.test.js checks
// they still match.
export const PLACEHOLDER_TEXTS = [
  "This is your first page — make it yours. Add photos, text, or anything else you'd like.",
  "Voici votre première page — faites-la vôtre. Ajoutez des photos, du texte, ou tout ce que vous voulez.",
  "Your caption",
  "Votre légende",
  "New text",
  "Nouveau texte",
  "Your text",
  "Votre texte",
];

// Spaces, case, kinds of apostrophes and dashes don't matter.
const normalize = (s) =>
  String(s ?? "")
    .replace(/[‘’ʼ]/g, "'")
    .replace(/[–—]/g, "-")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();

const PLACEHOLDERS = new Set(PLACEHOLDER_TEXTS.map(normalize));

export const isPlaceholderText = (content) => PLACEHOLDERS.has(normalize(content));

const keepItem = (item) => !(item?.type === "text" && isPlaceholderText(item.content));

/** The album as it should be printed: without the generic texts left as is. */
export function withoutPlaceholders(album) {
  if (!album) return album;
  const cover = { ...(album.cover || {}) };
  for (const key of ["extra_items", "back_extra_items"]) {
    if (Array.isArray(cover[key])) cover[key] = cover[key].filter(keepItem);
  }
  for (const key of ["spine_caption", "spine_subtitle", "subtitle", "back_text"]) {
    if (isPlaceholderText(cover[key])) cover[key] = "";
  }
  return {
    ...album,
    cover,
    pages: (album.pages || []).map((page) => ({ ...page, items: (page.items || []).filter(keepItem) })),
  };
}
