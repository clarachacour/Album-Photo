// One page per occasion (travel, couple, family), for the searches people
// make ("travel photo book", "album photo de famille"…): its text in the
// locale files (occasions.<occasion>), its covers from the templates.
export const OCCASIONS = {
  travel: {
    path: "/travel-photo-book",
    covers: [
      ["/theme-covers/travel-sicily.webp", "Sicily"],
      ["/theme-covers/travel-paros.webp", "Paros"],
      ["/theme-covers/travel-morocco.webp", "Morocco"],
      ["/theme-covers/travel-beirut.webp", "Beirut"],
    ],
  },
  couple: {
    path: "/couple-photo-album",
    covers: [
      ["/theme-covers/couple-notre-rencontre.webp", "Notre Rencontre"],
      ["/theme-covers/couple-notre-histoire.webp", "Notre Histoire"],
      ["/theme-covers/couple-forever-journey.webp", "Forever Journey"],
    ],
  },
  family: {
    path: "/family-photo-album",
    covers: [
      ["/theme-covers/family-mom.webp", "Mom"],
      ["/theme-covers/family-dad.webp", "Dad"],
      ["/theme-covers/celebrations-our-year.webp", "Our Year"],
    ],
  },
};
