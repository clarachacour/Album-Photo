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

/** Shows the card form for this session; resolves with its result (a JWT)
 *  once the customer has paid, rejects if the form is closed or fails. */
export async function payByCard(sessionJwt) {
  await loadScript(sessionLibrary(sessionJwt));
  if (!window.VAS?.UnifiedCheckout) throw new Error("VAS.UnifiedCheckout was not found");
  const client = await window.VAS.UnifiedCheckout(sessionJwt);
  const checkout = await client.createCheckout({ autoProcessing: true });
  // No containers: Cybersource's own sidebar (guide, 4.2).
  return checkout.mount();
}
