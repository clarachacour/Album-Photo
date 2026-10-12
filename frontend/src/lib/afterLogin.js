// Where to go once signed in: the page a signed-out visitor was heading
// to (e.g. "create an album with this template" from the home page) when
// they were sent to sign in. Kept for the tab only, read once.
const KEY = "everbook_after_login";

export function rememberAfterLogin(path) {
  try {
    sessionStorage.setItem(KEY, path);
  } catch {
    /* private mode: they land on the home page instead */
  }
}

export function takeAfterLogin(fallback = "/") {
  try {
    const path = sessionStorage.getItem(KEY);
    sessionStorage.removeItem(KEY);
    // Only one of our own pages, never another site.
    return path && path.startsWith("/") && !path.startsWith("//") ? path : fallback;
  } catch {
    return fallback;
  }
}
