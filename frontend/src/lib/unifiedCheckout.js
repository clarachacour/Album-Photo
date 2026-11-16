// Card payment with Cybersource Unified Checkout (areeba's gateway). The
// server opens the payment (POST /cart/card-session) and gives a "capture
// context": a JWT naming the script to load from Cybersource. That script
// shows the card form in Cybersource's own frames — the card number never
// goes through our page — and gives back a "transient token", sent with
// the order (POST /cart/checkout), which the server charges.
// See backend/app/services/cybersource.py.

/** The JSON inside a JWT (not checked: it comes from our own server). */
export function decodeJwtPayload(jwt) {
  const part = String(jwt || "").split(".")[1];
  if (!part) return null;
  try {
    const base64 = part.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(part.length / 4) * 4, "=");
    const text = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => `%${c.charCodeAt(0).toString(16).padStart(2, "0")}`)
        .join(""),
    );
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/** The Cybersource script the capture context asks for, and its hash. */
export function clientLibraryOf(captureContext) {
  const data = decodeJwtPayload(captureContext)?.ctx?.[0]?.data || {};
  const url = data.clientLibrary || "";
  let host = "";
  try {
    host = new URL(url).hostname;
  } catch {
    return null;
  }
  // Only ever Cybersource's own script.
  if (!url.startsWith("https://") || !(host === "cybersource.com" || host.endsWith(".cybersource.com"))) return null;
  return { url, integrity: data.clientLibraryIntegrity || "" };
}

const loading = {};

function loadScript({ url, integrity }) {
  if (!loading[url]) {
    loading[url] = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = url;
      if (integrity) {
        script.integrity = integrity;
        script.crossOrigin = "anonymous";
      }
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => {
        delete loading[url];
        script.remove();
        reject(new Error("card_script"));
      };
      document.head.appendChild(script);
    });
  }
  return loading[url];
}

/**
 * Shows the card form inside `containers` ({ paymentSelection, paymentScreen }:
 * CSS selectors) and resolves with the transient token once the customer
 * has entered their card. Rejects if the form can't be shown or is left.
 */
export async function showCardForm(captureContext, containers) {
  const library = clientLibraryOf(captureContext);
  if (!library) throw new Error("card_context");
  await loadScript(library);
  if (typeof window.Accept !== "function") throw new Error("card_script");
  const accept = await window.Accept(captureContext);
  // false: shown in the page's own containers, not in a sidebar.
  const unified = await accept.unifiedPayments(false);
  return unified.show({ containers });
}
