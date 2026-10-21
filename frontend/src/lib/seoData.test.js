import { describe, expect, it } from "vitest";
import en from "@/locales/en.json";
import { DIGITAL_PRICE, PAGE_TIERS, PRICE_TABLE, SHIPPING_PRICE } from "@/lib/pricing";
import { faqData, llmsTxt, productData } from "@/lib/seoData";

const SITE = "https://everbook-album.com";

describe("what search engines and AI assistants read", () => {
  it("states the site's real prices in llms.txt", () => {
    const text = llmsTxt(SITE, en.faq.items);
    for (const size of ["A5", "A4"]) {
      for (const pages of PAGE_TIERS) expect(text).toContain(`$${PRICE_TABLE[size][pages]} (${pages} pages)`);
    }
    expect(text).toContain(`PDF album $${DIGITAL_PRICE}`);
    expect(text).toContain(`delivery $${SHIPPING_PRICE} per order`);
    expect(text).toContain("costs $0.45 more");
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
    expect(text).toContain("### Can I get my album as a PDF?");
  });
});
