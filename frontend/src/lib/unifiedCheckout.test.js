import { describe, expect, it } from "vitest";
import { clientLibraryOf, decodeJwtPayload } from "./unifiedCheckout";

const jwt = (payload) => {
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  const b64 = btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `eyJhbGciOiJSUzI1NiJ9.${b64}.signature`;
};

const LIBRARY = "https://apitest.cybersource.com/up/v1/assets/0.31.0/SecureAcceptance.js";

describe("unifiedCheckout", () => {
  it("reads the capture context's payload, accents included", () => {
    expect(decodeJwtPayload(jwt({ name: "Été à Byblos", n: 1 }))).toEqual({ name: "Été à Byblos", n: 1 });
    expect(decodeJwtPayload("not a jwt")).toBeNull();
    expect(decodeJwtPayload("a.%%%.c")).toBeNull();
  });

  it("finds Cybersource's script and its hash", () => {
    const context = jwt({ ctx: [{ data: { clientLibrary: LIBRARY, clientLibraryIntegrity: "sha256-abc" } }] });
    expect(clientLibraryOf(context)).toEqual({ url: LIBRARY, integrity: "sha256-abc" });
  });

  it("never loads a script from anywhere else", () => {
    for (const url of ["https://evil.example/SecureAcceptance.js", "http://apitest.cybersource.com/x.js", "https://cybersource.com.evil.example/x.js", ""]) {
      expect(clientLibraryOf(jwt({ ctx: [{ data: { clientLibrary: url } }] }))).toBeNull();
    }
    expect(clientLibraryOf("garbage")).toBeNull();
  });
});
