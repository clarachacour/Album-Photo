// Lebanese phone numbers (delivery is in Lebanon only) — same rules as the
// backend's app/core/phone.py: with or without +961 / 00961 / 961, spaces,
// dashes, dots or brackets; mobiles 03 / 70 / 71 / 76 / 78 / 79 / 81,
// landlines 01 / 04-09, + 6 digits. Returns the 8-digit national number
// (e.g. "70123456"), or null when it isn't a Lebanese number.
const PREFIXES = ["03", "70", "71", "76", "78", "79", "81", "01", "04", "05", "06", "07", "08", "09"];

export function normalizeLebanesePhone(value) {
  let digits = String(value || "").replace(/[\s\-.()/]/g, "");
  if (digits.startsWith("+")) digits = digits.slice(1);
  if (!/^\d+$/.test(digits)) return null;
  let international = false;
  for (const code of ["00961", "961"]) {
    if (digits.startsWith(code) && [7, 8].includes(digits.length - code.length)) {
      digits = digits.slice(code.length);
      international = true;
      break;
    }
  }
  if (digits.length === 7 && (international || digits.startsWith("3"))) digits = `0${digits}`;
  return digits.length === 8 && PREFIXES.includes(digits.slice(0, 2)) ? digits : null;
}

export const isLebanesePhone = (value) => normalizeLebanesePhone(value) !== null;
