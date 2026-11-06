import { describe, expect, it, vi } from "vitest";
import { importWithRetry, textList } from "@/lib/i18n";

describe("when the texts can't be downloaded", () => {
  it("tries the download again before giving up", async () => {
    const load = vi.fn().mockRejectedValueOnce(new TypeError("Importing a module script failed.")).mockResolvedValue({ default: { a: 1 } });
    await expect(importWithRetry(load, 3, 1)).resolves.toEqual({ default: { a: 1 } });
    expect(load).toHaveBeenCalledTimes(2);
    const failing = vi.fn().mockRejectedValue(new TypeError("offline"));
    await expect(importWithRetry(failing, 3, 1)).rejects.toThrow("offline");
    expect(failing).toHaveBeenCalledTimes(3);
  });

  it("gives an empty list instead of breaking the page", () => {
    const missing = (key) => key; // i18next gives the key back when it has no text
    expect(textList(missing, "landing.hero.perks")).toEqual([]);
    const loaded = () => ["Made in Lebanon", "Delivered in Lebanon"];
    expect(textList(loaded, "landing.hero.perks")).toEqual(["Made in Lebanon", "Delivered in Lebanon"]);
  });
});
