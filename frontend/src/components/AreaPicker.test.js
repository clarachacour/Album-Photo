import { describe, expect, it } from "vitest";
import { matchAreas } from "@/components/AreaPicker";

describe("the delivery area list", () => {
  const areas = ["Achrafieh", "Hamra", "Jounieh", "Mar Mikhael", "Tripoli - Mina"];

  it("shows every area when nothing is typed", () => {
    expect(matchAreas(areas, "")).toEqual(areas);
  });

  it("puts the areas starting with what's typed first, ignoring case and accents", () => {
    expect(matchAreas(areas, "ha")).toEqual(["Hamra", "Mar Mikhael"]);
    expect(matchAreas(areas, "ACHRAFIÉH")).toEqual(["Achrafieh"]);
    expect(matchAreas(areas, "zzz")).toEqual([]);
  });
});
