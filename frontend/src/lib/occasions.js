// One page per occasion (travel, couple, family), for the searches people
// make ("travel photo book", "album photo de famille"…): its text in the
// locale files (occasions.<occasion>), its covers from the templates.
// Linked from the footer of every page (and listed in the sitemap and
// llms.txt), they lead visitors who arrive on them into the site.
// The covers are listed here rather than read from lib/coverThemes.js, a
// large file these pages, part of the site's first download, don't need.
export const OCCASIONS = {
  travel: {
    path: "/travel-photo-book",
    // Every travel template, as on the home page (a test checks they match).
    covers: [
      ["/theme-covers/travel-beirut.webp", "Beirut, Lebanon"],
      ["/theme-covers/travel-dubai.webp", "Dubai, UAE"],
      ["/theme-covers/travel-cyprus.webp", "Cyprus, Limassol"],
      ["/theme-covers/travel-cairo.webp", "Cairo, Egypt"],
      ["/theme-covers/travel-sicily.webp", "Sicily, Italy"],
      ["/theme-covers/travel-hawaii.webp", "Bali, Indonesia"],
      ["/theme-covers/travel-thailand.webp", "Thailand, Southeast Asia"],
      ["/theme-covers/travel-paros.webp", "Paros, Greece"],
      ["/theme-covers/travel-morocco.webp", "Morocco, Africa"],
      ["/theme-covers/travel-australia.webp", "Australia, Oceania"],
      ["/theme-covers/travel-barcelona.webp", "Barcelona, Catalonia"],
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
