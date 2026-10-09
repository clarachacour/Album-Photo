// The browsers built into apps (Instagram, Messenger, Facebook, TikTok…):
// links opened in those apps stay inside them, and Google sign-in doesn't
// work there (its window never comes back to the site). The site tries to
// move the person to their real browser instead.

const IN_APP = /FBAN|FBAV|FB_IAB|FBIOS|Instagram|Messenger|musical_ly|Bytedance|TikTok|Snapchat|\bLine\/|LinkedInApp|Twitter/i;

function userAgent() {
  return typeof navigator === "undefined" ? "" : navigator.userAgent || "";
}

/** "android" or "ios" when the page is open in an app's own browser, else null. */
export function inAppBrowser(ua = userAgent()) {
  if (!IN_APP.test(ua)) return null;
  if (/Android/i.test(ua)) return "android";
  if (/iPhone|iPad|iPod/i.test(ua)) return "ios";
  return null;
}

/**
 * Link that opens url in the phone's real browser: Chrome on Android (an
 * Android "intent"), Safari on iPhone (x-safari-https, iOS 17 and later, not
 * an official Apple feature: it can stop working).
 */
export function externalBrowserUrl(url, platform) {
  const u = new URL(url);
  if (platform === "android") {
    return `intent://${u.host}${u.pathname}${u.search}#Intent;scheme=${u.protocol.replace(":", "")};package=com.android.chrome;S.browser_fallback_url=${encodeURIComponent(url)};end`;
  }
  if (platform === "ios") return `x-safari-${url}`;
  return url;
}

const TRIED = "everbook_left_app_browser";

/**
 * On Android, moves the page to Chrome once per visit; if that doesn't work
 * the page stays where it is (and shows how to leave by hand).
 */
export function leaveAppBrowser() {
  if (typeof window === "undefined" || inAppBrowser() !== "android") return;
  try {
    if (sessionStorage.getItem(TRIED)) return;
    sessionStorage.setItem(TRIED, "1");
  } catch {
    return; // without a memory of the attempt it could repeat forever
  }
  window.location.href = externalBrowserUrl(window.location.href, "android");
}

/** Copies text to the clipboard, also in app browsers without the clipboard API. */
export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const field = document.createElement("textarea");
    field.value = text;
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.appendChild(field);
    field.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    field.remove();
    return ok;
  }
}
