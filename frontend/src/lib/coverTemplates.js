// 6 coffee-table cover templates using custom images
export const COVER_TEMPLATES = [
  {
    id: "australia",
    name: "Australia",
    image: "/images/covers/AUSTRALIA.png",
    mood: "Editorial style",
  },
  {
    id: "ibiza",
    name: "Ibiza",
    image: "/images/covers/IBIZA.png",
    mood: "Boho chic",
  },
  {
    id: "miami",
    name: "Miami",
    image: "/images/covers/MIAMI.png",
    mood: "Pastel coastal",
  },
  {
    id: "mykonos",
    name: "Mykonos",
    image: "/images/covers/MYKONOS.png",
    mood: "Aegean blue",
  },
  // Ajoute tes 2 autres images ici avec le même format :
  // {
  //   id: "nom-id",
  //   name: "Nom du livre",
  //   image: "/images/covers/NOM_IMAGE.jpg",
  //   mood: "Style",
  // },
];

export function getTemplate(id) {
  return COVER_TEMPLATES.find((t) => t.id === id) || COVER_TEMPLATES[0];
}