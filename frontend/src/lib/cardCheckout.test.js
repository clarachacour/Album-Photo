import { describe, expect, it } from "vitest";
import { decodeJwtPayload, sessionLibrary, sidebarMountOptions } from "@/lib/cardCheckout";

const jwt = (payload) => `h.${btoa(JSON.stringify(payload)).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_")}.s`;

describe("the card form's session", () => {
  it("names the script to load, with its integrity hash", () => {
    const session = jwt({ ctx: [{ data: { clientLibrary: "https://testup.cybersource.com/uc/v1/assets/sdk.js", clientLibraryIntegrity: "sha256-abc" } }] });
    expect(sessionLibrary(session)).toEqual({ url: "https://testup.cybersource.com/uc/v1/assets/sdk.js", integrity: "sha256-abc" });
  });

  it("refuses a session without a script or a malformed one", () => {
    expect(() => sessionLibrary(jwt({ ctx: [] }))).toThrow();
    expect(() => decodeJwtPayload("not-a-jwt")).toThrow();
  });
});

describe("showing the card form", () => {
  it("gives the SDK a container for its buttons and no paymentScreen (its sidebar)", () => {
    // The current SDK fails on a bare mount() (reads undefined.paymentScreen).
    expect(sidebarMountOptions("#uc-payment-buttons")).toEqual({ paymentSelection: "#uc-payment-buttons" });
  });
});
