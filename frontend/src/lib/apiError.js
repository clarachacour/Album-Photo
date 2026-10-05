/**
 * A message to show for a failed API call. The server's own message when it
 * sent one; otherwise what actually went wrong, rather than a bare "An error
 * occurred" that says nothing to the person (or to us when they report it).
 */
export function apiErrorMessage(err, t) {
  const res = err?.response;
  // No answer at all: offline, the server unreachable, or the request
  // blocked by the browser (an extension, or a site address the server
  // doesn't accept).
  if (!res) return t("auth.networkError");
  const detail = res.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  // Form checks (422) come as a list: the first problem, in words.
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg).replace(/^Value error, /, "");
  return `${t("auth.genericError")} (${res.status})`;
}
