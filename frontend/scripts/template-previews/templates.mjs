import { createServer } from "vite";
const server = await createServer({ root: process.cwd(), server: { middlewareMode: true, hmr: false }, appType: "custom", logLevel: "error" });
const { COVER_THEMES } = await server.ssrLoadModule("/src/lib/coverThemes.js");
const { DEFAULT_COVER } = await server.ssrLoadModule("/src/lib/coverTemplates.js");
const out = [];
for (const theme of COVER_THEMES) for (const t of theme.templates) {
  const c = t.cover || {};
  out.push({ id: t.id, theme: theme.id, title: t.title, landingImage: t.landingImage, cover: {
    bg_color: DEFAULT_COVER.bg_color, accent_color: DEFAULT_COVER.accent_color, text_color: DEFAULT_COVER.text_color,
    title_font: DEFAULT_COVER.title_font, title_font_weight: DEFAULT_COVER.title_font_weight, ...c,
    extra_items: (c.extra_items || []).map((it, i) => ({ ...it, id: `i${i}`, template_item_id: it.id })),
    back_extra_items: (c.back_extra_items || []).map((it, i) => ({ ...it, id: `b${i}` })),
  }});
}
console.log(JSON.stringify(out));
await server.close();
