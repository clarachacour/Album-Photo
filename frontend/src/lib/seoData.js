// What search engines and AI assistants read about Everbook, made from the
// site's own data (prices, FAQ) so it never says something the site doesn't:
// schema.org data for the pages (scripts/prerender.mjs) and llms.txt.
import { DIGITAL_PRICE, PAGE_TIERS, PRICE_TABLE, SHIPPING_PRICE } from "@/lib/pricing";

const SIZES = { A5: "A5 (14.8 × 21 cm)", A4: "A4 (21 × 29.7 cm)" };

/** The printed albums and the PDF, with their prices, delivered in Lebanon. */
export function productData(siteUrl) {
  const shipping = {
    "@type": "OfferShippingDetails",
    shippingRate: { "@type": "MonetaryAmount", value: SHIPPING_PRICE, currency: "USD" },
    shippingDestination: { "@type": "DefinedRegion", addressCountry: "LB" },
    deliveryTime: {
      "@type": "ShippingDeliveryTime",
      handlingTime: { "@type": "QuantitativeValue", minValue: 3, maxValue: 3, unitCode: "DAY" },
      transitTime: { "@type": "QuantitativeValue", minValue: 2, maxValue: 3, unitCode: "DAY" },
    },
  };
  const printed = Object.entries(PRICE_TABLE).map(([size, prices]) => ({
    "@type": "Product",
    "@id": `${siteUrl}/#album-${size.toLowerCase()}`,
    name: `Everbook printed photo album — ${size}`,
    description: `A hardcover photo book in ${SIZES[size]}, portrait or landscape, made from your own photos: laid out for you, printed and delivered in Lebanon.`,
    brand: { "@id": `${siteUrl}/#organization` },
    image: `${siteUrl}/og-image.jpg`,
    offers: {
      "@type": "AggregateOffer",
      priceCurrency: "USD",
      lowPrice: Math.min(...Object.values(prices)),
      highPrice: Math.max(...Object.values(prices)),
      offerCount: PAGE_TIERS.length,
      offers: PAGE_TIERS.map((pages) => ({
        "@type": "Offer",
        name: `${size}, ${pages} pages`,
        price: prices[pages],
        priceCurrency: "USD",
        availability: "https://schema.org/InStock",
        areaServed: { "@type": "Country", name: "Lebanon" },
        shippingDetails: shipping,
        url: `${siteUrl}/`,
      })),
    },
  }));
  const digital = {
    "@type": "Product",
    "@id": `${siteUrl}/#album-pdf`,
    name: "Everbook digital photo album (PDF)",
    description: "Your photo album as a PDF to download and keep: cover, pages and back cover, in screen quality.",
    brand: { "@id": `${siteUrl}/#organization` },
    offers: { "@type": "Offer", price: DIGITAL_PRICE, priceCurrency: "USD", availability: "https://schema.org/InStock", url: `${siteUrl}/` },
  };
  return [...printed, digital];
}

/** The FAQ page's questions and answers. */
export function faqData(siteUrl, items) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "@id": `${siteUrl}/faq#faq`,
    mainEntity: items.map((it) => ({
      "@type": "Question",
      name: it.q,
      acceptedAnswer: { "@type": "Answer", text: it.a },
    })),
  };
}

/** llms.txt: the site in plain text, for AI assistants (llmstxt.org). */
export function llmsTxt(siteUrl, faqItems) {
  const price = (size) => PAGE_TIERS.map((p) => `$${PRICE_TABLE[size][p]} (${p} pages)`).join(", ");
  return [
    "# Everbook",
    "",
    "> Everbook (everbook-album.com) is an online photo book service in Lebanon: you upload your photos, the album is laid out for you in minutes, then printed and delivered to your door anywhere in Lebanon. Also known as Everbook Album.",
    "",
    "## Key facts",
    "",
    "- What: printed hardcover photo albums (photo books) made from your own photos, and the same album as a PDF.",
    "- How: upload all your photos, even unsorted; Everbook removes duplicates and blurry shots, orders the rest by date and place and lays out the album; you personalize it (cover templates, layouts, text) in an online editor, on phone or computer.",
    "- Where: delivery everywhere in Lebanon (Beirut, Mount Lebanon, Jounieh, Byblos, Tripoli, Saida, Tyre, Zahle…), to the door, by courier.",
    `- Prices (US dollars): A5 printed album ${price("A5")}; A4 printed album ${price("A4")}; PDF album $${DIGITAL_PRICE}; delivery $${SHIPPING_PRICE} per order, whatever the number of albums.`,
    "- Timing: printing about 3 days, delivery 2 to 3 days.",
    "- Payment: printed albums are paid in cash on delivery.",
    "- Gift cards: offer an album (format and page count chosen), received as a PDF; the recipient creates their own album with the code, delivery included.",
    "- Languages: English and French.",
    "- Contact: orders@everbook-album.com · Instagram: https://www.instagram.com/everbook_album/",
    "",
    "## Pages",
    "",
    `- [Home — create your album](${siteUrl}/): how it works, templates, prices`,
    `- [Gift an album](${siteUrl}/gift): gift cards`,
    `- [FAQ](${siteUrl}/faq): formats, prices, delivery, PDF, gifts`,
    `- [Shipping](${siteUrl}/shipping): delivery in Lebanon`,
    `- [Terms of sale](${siteUrl}/terms)`,
    `- [Contact](${siteUrl}/contact)`,
    "",
    "## FAQ",
    "",
    ...faqItems.flatMap((it) => [`### ${it.q}`, "", it.a, ""]),
  ].join("\n");
}
