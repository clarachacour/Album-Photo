// Page templates for each page orientation — the same file the backend's
// automatic layout reads (layoutTemplates.json, made by
// backend/scripts/gen_layout_templates.py; a backend test checks both copies
// are identical), so a layout picked by hand looks exactly like one the AI
// would have made.
import templates from "./layoutTemplates.json";

/** Fraction of a photo a frame may cut off to fill its slot exactly. */
export const MAX_CROP = templates.max_crop;

/** { name: { label_fr, label_en, slots: [{ x, y, w, h }] } } for a page orientation. */
export function layoutTemplates(orientation) {
  return templates[orientation === "landscape" ? "landscape" : "portrait"];
}

/** Templates grouped by photo count, for the layout menu: [{ count, patterns: [name] }]. */
export function layoutGroups(orientation) {
  const groups = new Map();
  for (const [name, template] of Object.entries(layoutTemplates(orientation))) {
    const count = template.slots.length;
    if (!groups.has(count)) groups.set(count, []);
    groups.get(count).push(name);
  }
  return [...groups.entries()].sort((a, b) => a[0] - b[0]).map(([count, patterns]) => ({ count, patterns }));
}

export function templateLabel(template, language) {
  return (language || "").startsWith("fr") ? template.label_fr : template.label_en;
}

/** The one-photo, full-page template (a new blank page). */
export function fullPageTemplate(orientation) {
  const all = layoutTemplates(orientation);
  const name = orientation === "landscape" ? "l_full" : "p_full";
  return { name, ...all[name] };
}
