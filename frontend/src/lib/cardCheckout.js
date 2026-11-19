// Card payment: Cybersource's Unified Checkout (through areeba), as its
// guide describes — the session (a JWT from our server) names the script to
// load (clientLibrary, with its integrity hash); the script shows the card
// form (its own sidebar: the card is typed there, never on our site) and
// returns the result. The result only tells our server which transaction to
// check: it's never taken as proof of payment here.

/** The JWT's payload (not checked here: the server checks the payment). */
export function decodeJwtPayload(jwt) {
  const parts = String(jwt || "").split(".");
  if (parts.length !== 3) throw new Error("Invalid JWT format");
  let payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
  while (payload.length % 4) payload += "=";
  return JSON.parse(atob(payload));
}

/** The script the session asks for: { url, integrity }. */
export function sessionLibrary(sessionJwt) {
  const ctx = decodeJwtPayload(sessionJwt)?.ctx?.[0]?.data || {};
  if (!ctx.clientLibrary) throw new Error("clientLibrary not found in session JWT");
  return { url: ctx.clientLibrary, integrity: ctx.clientLibraryIntegrity || null };
}

function loadScript({ url, integrity }) {
  return new Promise((resolve, reject) => {
    document.getElementById("uc-sdk")?.remove();
    const script = document.createElement("script");
    script.id = "uc-sdk";
    script.src = url;
    script.crossOrigin = "anonymous";
    if (integrity) script.integrity = integrity;
    script.onload = resolve;
    script.onerror = () => reject(new Error("Failed to load the card form"));
    document.head.appendChild(script);
  });
}

/** The element the payment buttons go in, once the page has drawn it. */
async function waitForElement(selector, ms = 3000) {
  const until = Date.now() + ms;
  while (!document.querySelector(selector)) {
    if (Date.now() > until) throw new Error(`Container not found: ${selector}`);
    await new Promise((r) => setTimeout(r, 50));
  }
}

/** The SDK's mount options for the sidebar: its payment buttons (card,
 *  wallets) in our container, and no paymentScreen — the card form then
 *  opens as Cybersource's own side panel. (Its current SDK needs the
 *  paymentSelection container: a bare mount() fails, despite the guide's
 *  4.2 sample.) */
export function sidebarMountOptions(container) {
  return { paymentSelection: container };
}

/** Shows the payment buttons in `container`, then the card form in a side
 *  panel; resolves with its result (a JWT) once the customer has paid,
 *  rejects if the form fails — or as soon as `signal` aborts (the
 *  customer's "Cancel": the error then has cancelled = true). */
export async function payByCard(sessionJwt, { container = "#uc-payment-buttons", signal } = {}) {
  await loadScript(sessionLibrary(sessionJwt));
  if (!window.VAS?.UnifiedCheckout) throw new Error("VAS.UnifiedCheckout was not found");
  const client = await window.VAS.UnifiedCheckout(sessionJwt);
  const checkout = await client.createCheckout({ autoProcessing: true });
  await waitForElement(container);
  const mounted = checkout.mount(sidebarMountOptions(container));
  if (!signal) return mounted;
  const cancelled = new Promise((_, reject) => {
    const stop = () => {
      try {
        checkout.destroy?.();
      } catch {
        // Already gone.
      }
      const err = new Error("Cancelled by the customer");
      err.cancelled = true;
      reject(err);
    };
    if (signal.aborted) stop();
    else signal.addEventListener("abort", stop, { once: true });
  });
  return Promise.race([mounted, cancelled]);
}
