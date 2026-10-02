/**
 * A date sent by the server. Its times have 6 digits after the seconds
 * ("10:58:10.025397"), while the JavaScript date format only provides for 3:
 * some Safari versions then show "Invalid Date". Cut to 3 before reading.
 */
export function parseDate(value) {
  if (!value) return new Date(NaN);
  return new Date(String(value).replace(/(\.\d{3})\d+/, "$1"));
}
