import { describe, expect, it } from "vitest";
import en from "@/locales/en.json";
import fr from "@/locales/fr.json";
import { DIGITAL_PRICE, PAGE_TIERS, PRICE_TABLE, SHIPPING_PRICE } from "@/lib/pricing";
import { faqData, llmsTxt, productData } from "@/lib/seoData";

const SITE = "https://everbook-album.com";

describe("what search engines and AI assistants read", () => {
  it("states the site's real prices in the FAQ, in both languages", () => {
    for (const locale of [en, fr]) {
      const answer = locale.faq.items.find((it) => /\$/.test(it.a) && /150/.test(it.a)).a;
      for (const size of ["A5", "A4"]) {
        for (const pages of PAGE_TIERS) expect(answer).toMatch(new RegExp(`\\b${PRICE_TABLE[size][pages]}\\b`));
      }
      expect(answer).toMatch(new RegExp(`\\b${DIGITAL_PRICE}\\b`));
      expect(answer).toMatch(new RegExp(`\\b${SHIPPING_PRICE}\\b`));
    }
  });

  it("lists every album with its prices, delivered in Lebanon", () => {
    const [a5, a4, pdf] = productData(SITE);
    expect(a5.offers.offers.map((o) => o.price)).toEqual(PAGE_TIERS.map((p) => PRICE_TABLE.A5[p]));
    expect(a4.offers.lowPrice).toBe(PRICE_TABLE.A4[24]);
    expect(a4.offers.offers[0].shippingDetails.shippingRate.value).toBe(SHIPPING_PRICE);
    expect(pdf.offers.price).toBe(DIGITAL_PRICE);
  });

  it("marks the FAQ up as questions and answers, and sums the site up in llms.txt", () => {
    const faq = faqData(SITE, en.faq.items);
    expect(faq["@type"]).toBe("FAQPage");
    expect(faq.mainEntity[0].name).toBe("Where can I make a photo album in Lebanon?");
    const text = llmsTxt(SITE, en.faq.items);
    expect(text.startsWith("# Everbook\n")).toBe(true);
    expect(text).toContain(`$${PRICE_TABLE.A4[150]} (150 pages)`);
    expect(text).toContain("### How much does a photo album cost?");
  });
});
