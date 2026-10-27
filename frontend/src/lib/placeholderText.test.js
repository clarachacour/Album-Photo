import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import en from "@/locales/en.json";
import fr from "@/locales/fr.json";
import { PLACEHOLDER_TEXTS, isPlaceholderText, withoutPlaceholders } from "@/lib/placeholderText";

describe("generic texts left in an album", () => {
  it("knows the site's generic texts, in both languages", () => {
    for (const locale of [en, fr]) {
      for (const text of [locale.albumEditor.yourCaption, locale.coverPanel.newText, locale.coverPanel.yourText]) {
        expect(PLACEHOLDER_TEXTS).toContain(text);
      }
    }
    // The first page's hint, as the backend writes it.
    const layout = readFileSync(new URL("../../../backend/app/services/layout.py", import.meta.url), "utf8");
    for (const hint of PLACEHOLDER_TEXTS.slice(0, 2)) expect(layout).toContain(hint);
  });

  it("recognizes them however they were spaced or capitalized", () => {
    expect(isPlaceholderText("  your CAPTION ")).toBe(true);
    expect(isPlaceholderText("This is your first page - make it yours. Add photos, text, or anything else you’d like.")).toBe(true);
    expect(isPlaceholderText("Our caption")).toBe(false);
    expect(isPlaceholderText("")).toBe(false);
  });

  it("leaves them out of the printed album, and nothing else", () => {
    const album = {
      title: "Byblos",
      cover: {
        title: "Byblos",
        spine_caption: "Your text",
        extra_items: [{ id: "a", type: "text", content: "New text" }, { id: "b", type: "image", asset: "logo" }],
      },
      pages: [
        {
          id: "p1",
          items: [
            { id: "t", type: "text", content: "Byblos" },
            { id: "h", type: "text", content: "Voici votre première page — faites-la vôtre. Ajoutez des photos, du texte, ou tout ce que vous voulez." },
            { id: "c", type: "text", content: "Votre légende" },
            { id: "ph", type: "photo", photo_id: "x" },
          ],
        },
      ],
    };
    const printed = withoutPlaceholders(album);
    expect(printed.pages[0].items.map((i) => i.id)).toEqual(["t", "ph"]);
    expect(printed.cover.extra_items.map((i) => i.id)).toEqual(["b"]);
    expect(printed.cover.spine_caption).toBe("");
    expect(printed.cover.title).toBe("Byblos");
    expect(album.pages[0].items).toHaveLength(4); // the album itself is unchanged
  });
});
