// The default cover logo (coral). A file in public/cover-art, not an
// embedded image: albums keep a copy of their logo's address in their cover,
// which stays a few bytes instead of 170 KB resent with every save. Never
// change a file there — add a new "-v2" one instead: saved albums point to
// the old address, and browsers keep these files for a year.
export const CORAL_LOGO_URL = "/cover-art/coral-logo-v1.webp";
