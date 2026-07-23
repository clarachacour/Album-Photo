// 6 coffee-table cover templates. Kept in sync with backend server.py.
export const COVER_TEMPLATES = [
  {
    id: "teal-coral",
    name: "Océan Corail",
    bg: "#0F5A67",
    accent: "#E56B55",
    text: "#F9F8F6",
    illustration: "coral",
    mood: "Édition tropicale — vibrant & marin",
  },
  {
    id: "sand-forest",
    name: "Sable & Forêt",
    bg: "#D5C9B3",
    accent: "#2C402E",
    text: "#1A1A17",
    illustration: "leaf",
    mood: "Nature calme — botanique",
  },
  {
    id: "navy-blush",
    name: "Marine & Blush",
    bg: "#1C2D42",
    accent: "#E8D5D1",
    text: "#F9F8F6",
    illustration: "wave",
    mood: "Élégant — soirée & lumière",
  },
  {
    id: "terracotta-cream",
    name: "Terracotta",
    bg: "#C05B3F",
    accent: "#F5EBDC",
    text: "#F9F8F6",
    illustration: "sun",
    mood: "Chaud — sud & désert",
  },
  {
    id: "forest-gold",
    name: "Forêt & Or",
    bg: "#2C402E",
    accent: "#C9A959",
    text: "#F9F8F6",
    illustration: "mountain",
    mood: "Aventure — montagne & bois",
  },
  {
    id: "charcoal-rose",
    name: "Charbon & Rose",
    bg: "#2A2A28",
    accent: "#D89A9E",
    text: "#F9F8F6",
    illustration: "bird",
    mood: "Éditorial — urbain & mode",
  },
];

export function getTemplate(id) {
  return COVER_TEMPLATES.find((t) => t.id === id) || COVER_TEMPLATES[0];
}
