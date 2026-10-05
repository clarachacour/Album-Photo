import { describe, expect, it } from "vitest";
import { apiErrorMessage } from "@/lib/apiError";

const t = (k) => ({ "auth.networkError": "NETWORK", "auth.genericError": "GENERIC" })[k];

describe("apiErrorMessage", () => {
  it("says the server couldn't be reached when there was no answer", () => {
    expect(apiErrorMessage(new Error("Network Error"), t)).toBe("NETWORK");
  });
  it("shows the server's own message", () => {
    expect(apiErrorMessage({ response: { status: 400, data: { detail: "Email already registered" } } }, t)).toBe("Email already registered");
  });
  it("shows the first form problem of a 422", () => {
    const err = { response: { status: 422, data: { detail: [{ msg: "value is not a valid email address: An email address must have an @-sign." }] } } };
    expect(apiErrorMessage(err, t)).toBe("value is not a valid email address: An email address must have an @-sign.");
  });
  it("adds the status code to the generic message", () => {
    expect(apiErrorMessage({ response: { status: 503, data: "Service Unavailable" } }, t)).toBe("GENERIC (503)");
  });
});
