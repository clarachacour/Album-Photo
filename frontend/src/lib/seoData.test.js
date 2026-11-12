import { describe, expect, it } from "vitest";
import i18next from "i18next";
import en from "@/locales/en.json";
import fr from "@/locales/fr.json";
import { DIGITAL_PRICE, PAGE_TIERS, PRICE_TABLE, PRICE_TEXT, SHIPPING_PRICE } from "@/lib/pricing";
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
    expect(text).toContain("costs $0.60 more");
  });

  it("lists every album with its prices, delivered in Lebanon, as Google's merchant listings expect", () => {
    const products = productData(SITE);
    const [a5, a4] = products;
    expect(a5.offers.map((o) => o.price)).toEqual(PAGE_TIERS.map((p) => PRICE_TABLE.A5[p]));
    expect(a4.offers[0].price).toBe(PRICE_TABLE.A4[24]);
    for (const product of products) {
      expect(product.image.length).toBeGreaterThan(0);
      expect(product.brand["@type"]).toBe("Brand");
      for (const o of product.offers) {
        expect(o.shippingDetails.shippingDestination.addressCountry).toBe("LB");
        expect(o.hasMerchantReturnPolicy.applicableCountry).toBe("LB");
      }
    }
    expect(a4.offers[0].shippingDetails.shippingRate.value).toBe(SHIPPING_PRICE);
    // The PDF only once it can be ordered.
    expect(products.find((p) => p["@id"].endsWith("#album-pdf"))?.offers[0].price ?? DIGITAL_PRICE).toBe(DIGITAL_PRICE);
  });

  it("marks the FAQ up as questions and answers, and sums the site up in llms.txt", () => {
    const faq = faqData(SITE, en.faq.items);
    expect(faq["@type"]).toBe("FAQPage");
    expect(faq.mainEntity[0].name).toBe("Where can I make a photo album in Lebanon?");
    const text = llmsTxt(SITE, en.faq.items);
    expect(text.startsWith("# Everbook\n")).toBe(true);
    expect(text).toContain("### Can I get my album as a PDF?");
  });

  it("gives the prices on the pricing page, in its language, where they are shown", () => {
    const [a5En] = productData(SITE);
    expect(a5En.offers[0].url).toBe(`${SITE}/pricing`);
    const [a5Fr] = productData(SITE, "fr");
    expect(a5Fr.name).toBe("Album photo imprimé Everbook — A5");
    expect(a5Fr.offers[0].url).toBe(`${SITE}/fr/pricing`);
    expect(a5Fr.offers.map((o) => o.price)).toEqual(a5En.offers.map((o) => o.price));
  });

  it("quotes the price table's own prices in the FAQ, in both languages", async () => {
    for (const [lng, resources] of [["en", en], ["fr", fr]]) {
      const i18n = i18next.createInstance();
      await i18n.init({ lng, resources: { [lng]: { translation: resources } }, interpolation: { escapeValue: false } });
      const items = i18n.t("faq.items", { ...PRICE_TEXT, returnObjects: true });
      const answer = items.find((it) => /\/pricing/.test(it.a))?.a;
      expect(answer, lng).toBeTruthy();
      expect(answer).not.toContain("{{");
      for (const price of [PRICE_TABLE.A5[24], PRICE_TABLE.A4[24], PRICE_TABLE.A5[150], PRICE_TABLE.A4[150], SHIPPING_PRICE]) {
        expect(answer).toContain(String(price));
      }
    }
  });
});
