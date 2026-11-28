// The drawings anyone can put on a cover ("Drawing" in the cover editor):
// the templates' own, each in its latest version (files in
// public/cover-art). aspect: width ÷ height of the drawing's frame.
export const COVER_DRAWINGS = [
  { key: "beirut-windows", url: "/cover-art/travel-beirut-v2.svg", aspect: 1200 / 680, name: "Beirut windows" },
  { key: "beirut-coffee", url: "/cover-art/travel-beirut-v1.svg", aspect: 1230 / 960, name: "Lebanese coffee cups" },
  { key: "barcelona", url: "/cover-art/travel-barcelona-v2.svg", aspect: 569 / 672, name: "Sagrada Família" },
  { key: "cairo", url: "/cover-art/travel-cairo-v4.svg", aspect: 3220 / 2260, name: "Pyramids" },
  { key: "cyprus", url: "/cover-art/travel-cyprus-v1.svg", aspect: 3826 / 3722, name: "Cyprus columns" },
  { key: "dubai-tower", url: "/cover-art/travel-dubai-v1.svg", aspect: 660 / 1200, name: "Burj Al Arab" },
  { key: "dubai-skyline", url: "/cover-art/travel-dubai-v3.svg", aspect: 2475 / 2174, name: "Dubai skyline" },
  { key: "hawaii", url: "/cover-art/travel-hawaii-v2.svg", aspect: 737 / 724, name: "Surfer" },
  { key: "morocco", url: "/cover-art/travel-morocco-v2.svg", aspect: 1024 / 824, name: "Camel" },
  { key: "paros", url: "/cover-art/travel-paros-v2.svg", aspect: 702 / 711, name: "Evil eye" },
  { key: "sicily", url: "/cover-art/travel-sicily-v2.svg", aspect: 372 / 677, name: "Lemon" },
  { key: "thailand", url: "/cover-art/travel-thailand-v2.svg", aspect: 765 / 699, name: "Thai temple" },
  { key: "australia", url: "/cover-art/travel-australia-v1.svg", aspect: 714 / 481, name: "Kangaroo" },
  { key: "globe", url: "/cover-art/globe-v2.svg", aspect: 1, name: "Globe" },
  { key: "van", url: "/cover-art/van-v2.svg", aspect: 600 / 420, name: "Camper van" },
  { key: "pasta", url: "/cover-art/pasta-v3.svg", aspect: 520 / 315, name: "Plate of pasta" },
  { key: "coral", url: "/cover-art/coral-logo-v2.svg", aspect: 1732 / 1946, name: "Coral" },
  { key: "dove", url: "/cover-art/baptism-dove-v1.svg", aspect: 130 / 110, name: "Dove" },
  { key: "rings-heart", url: "/cover-art/rings-logo-v2.svg", aspect: 382 / 319, name: "Rings with a heart" },
  { key: "rings-gold", url: "/cover-art/ouryear-rings-logo-v2.svg", aspect: 399 / 306, name: "Gold rings" },
  { key: "heart", url: "/cover-art/heart-logo-v2.svg", aspect: 485 / 445, name: "Carved heart" },
  { key: "pink-heart", url: "/cover-art/mom-heart-logo-v2.svg", aspect: 458 / 470, name: "Pink heart" },
  { key: "compass", url: "/cover-art/dad-compass-logo-v2.svg", aspect: 436 / 436, name: "Compass" },
];

/** The box of a drawing just added: centred, its own shape, about half the page. */
export function drawingBox(aspect, pageAspectWH) {
  let w = 0.5;
  let h = (w / aspect) * pageAspectWH;
  if (h > 0.45) {
    h = 0.45;
    w = (h * aspect) / pageAspectWH;
  }
  return { x: (1 - w) / 2, y: (1 - h) / 2, w, h };
}
