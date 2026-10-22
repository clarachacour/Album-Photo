import { describe, expect, it } from "vitest";
import en from "@/locales/en.json";
import fr from "@/locales/fr.json";
import { isPublicPage, localePath, splitLocale } from "@/lib/localePath";

describe("the public pages in two languages", () => {
  it("puts a public page's French version under /fr", () => {
    expect(localePath("/", "fr")).toBe("/fr");
    expect(localePath("/faq", "fr")).toBe("/fr/faq");
    expect(localePath("/faq#delivery", "fr-FR")).toBe("/fr/faq#delivery");
    expect(localePath("/fr/gift", "en")).toBe("/gift");
    expect(localePath("/", "en")).toBe("/");
  });

  it("leaves the app's other pages at their one address", () => {
    expect(localePath("/dashboard", "fr")).toBe("/dashboard");
    expect(localePath("/auth?mode=login", "fr")).toBe("/auth?mode=login");
    expect(isPublicPage("/cart")).toBe(false);
  });

  it("reads the language from the address", () => {
    expect(splitLocale("/fr")).toEqual({ lng: "fr", path: "/" });
    expect(splitLocale("/fr/faq")).toEqual({ lng: "fr", path: "/faq" });
    expect(splitLocale("/faq")).toEqual({ lng: null, path: "/faq" });
    expect(splitLocale("/francais")).toEqual({ lng: null, path: "/francais" });
  });
});

// A visitor downloads only their language's texts: each file must have
// every text, or the visitor would see a raw key.
describe("the two languages have the same texts", () => {
  const keys = (obj, prefix = "") =>
    Object.entries(obj).flatMap(([k, v]) => (v && typeof v === "object" && !Array.isArray(v) ? keys(v, `${prefix}${k}.`) : [`${prefix}${k}`]));
  it("every English text exists in French, and the other way round", () => {
    const enKeys = new Set(keys(en));
    const frKeys = new Set(keys(fr));
    // i18next plural forms differ between languages (e.g. _many in French).
    const plural = (k) => /_(zero|one|two|few|many|other)$/.test(k);
    expect([...enKeys].filter((k) => !frKeys.has(k) && !plural(k))).toEqual([]);
    expect([...frKeys].filter((k) => !enKeys.has(k) && !plural(k))).toEqual([]);
  });
});
