// Detects whether the current browser is genuinely running on a phone (or
// small tablet), as opposed to just a narrow desktop window — screen width
// alone is a poor signal for this (a resized desktop browser window can be
// just as narrow as a phone), so this checks the user agent for the actual
// device tokens browsers report instead. Used to skip offering options that
// only make sense when the person is on a *different* device than the one
// they're using right now — e.g. "scan this QR code with your phone" is
// nonsensical advice to someone already on their phone.
export function isMobileDevice() {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent || navigator.vendor || "";
  return /Android|iPhone|iPod|BlackBerry|IEMobile|Opera Mini/i.test(ua) ||
    // Modern iPadOS reports itself as a desktop Mac user agent, but still
    // exposes touch support the way a real Mac never does — this second
    // check catches that case (and other touch-first tablets) without
    // relying on the user agent string alone.
    (/Macintosh/i.test(ua) && navigator.maxTouchPoints > 1);
}
