import { describe, expect, it } from "vitest";
import { COVER_THEMES } from "@/lib/coverThemes";
import { defaultLogoItem } from "@/lib/coverTemplates";
import {
  DEFAULT_TITLE_BOX,
  NEW_ITEM_BOX,
  defaultItemBox,
  defaultSpineBox,
  defaultTitleBox,
} from "@/lib/coverDefaults";

const ALL_TEMPLATES = COVER_THEMES.flatMap((theme) => theme.templates);
const box = (it) => ({ x: it.x, y: it.y, w: it.w, h: it.h });
const moved = (it) => ({ ...it, x: 0.9, y: 0.9, w: 0.05, h: 0.05 });

// Same copy CreateAlbum makes when an album is created from a template.
// `linked: false` reproduces albums created before template_item_id existed.
function albumFromTemplate(template, { linked }) {
  let n = 0;
  const copy = (items = []) =>
    items.map((it) => ({ ...it, id: `random-${n++}`, ...(linked ? { template_item_id: it.id } : {}) }));
  return {
    cover_template_id: template.id,
    cover: {
      ...template.cover,
      extra_items: copy(template.cover.extra_items),
      back_extra_items: copy(template.cover.back_extra_items),
    },
  };
}

describe("defaultTitleBox", () => {
  it("returns the template's title position", () => {
    const sicily = ALL_TEMPLATES.find((t) => t.id === "travel-sicily");
    expect(defaultTitleBox({ cover_template_id: "travel-sicily" })).toEqual({
      x: sicily.cover.title_x,
      y: sicily.cover.title_y,
      w: sicily.cover.title_w,
      h: sicily.cover.title_h,
    });
  });

  it("falls back to the position the cover renders by default", () => {
    expect(defaultTitleBox({ cover_template_id: "default" })).toEqual(DEFAULT_TITLE_BOX);
  });
});

describe("defaultItemBox puts every template element back in its place", () => {
  for (const template of ALL_TEMPLATES) {
    for (const linked of [true, false]) {
      it(`${template.id}${linked ? "" : " (album created before the fix)"}`, () => {
        const album = albumFromTemplate(template, { linked });
        for (const side of ["front", "back"]) {
          const key = side === "back" ? "back_extra_items" : "extra_items";
          const original = template.cover[key] || [];
          album.cover[key].forEach((item, i) => {
            expect(defaultItemBox(album, moved(item), side), `${side} item ${original[i].id}`).toEqual(box(original[i]));
          });
        }
      });
    }
  }
});

describe("defaultItemBox for elements added in the editor", () => {
  it("returns where a new element of that type appears", () => {
    const album = albumFromTemplate(ALL_TEMPLATES[0], { linked: true });
    for (const type of ["text", "shape", "image"]) {
      const added = { id: `added-${type}`, type, is_photo: type === "image", x: 0.7, y: 0.7, w: 0.1, h: 0.1 };
      album.cover.extra_items.push(added);
      expect(defaultItemBox(album, added, "front")).toEqual(NEW_ITEM_BOX[type]);
    }
  });

  it("puts the default logo of an album without template back in place", () => {
    const logo = { ...defaultLogoItem(), id: "random" };
    const album = { cover_template_id: "default", cover: { extra_items: [logo] } };
    expect(defaultItemBox(album, moved(logo), "front")).toEqual(box(defaultLogoItem()));
  });
});

describe("defaultSpineBox", () => {
  it("returns the template's spine position, null where it has none", () => {
    const template = ALL_TEMPLATES.find((t) => t.cover.spine_title_y != null);
    const result = defaultSpineBox({ cover_template_id: template.id }, "spine_title");
    expect(result.spine_title_y).toBe(template.cover.spine_title_y);
    expect(Object.keys(result).sort()).toEqual(["spine_title_h", "spine_title_w", "spine_title_x", "spine_title_y"]);
  });

  it("clears the position when there is no template (the spine places it itself)", () => {
    expect(defaultSpineBox({ cover_template_id: "default" }, "spine_year")).toEqual({
      spine_year_x: null,
      spine_year_y: null,
      spine_year_w: null,
      spine_year_h: null,
    });
  });
});
