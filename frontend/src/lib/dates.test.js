import { describe, expect, it } from "vitest";
import { parseDate } from "./dates";

describe("parseDate", () => {
  it("reads server dates with microseconds", () => {
    expect(parseDate("2026-09-30T17:58:10.025397+00:00").toISOString()).toBe("2026-09-30T17:58:10.025Z");
  });
  it("reads dates without fractions", () => {
    expect(parseDate("2026-10-09T00:00:00+00:00").toISOString()).toBe("2026-10-09T00:00:00.000Z");
  });
  it("is an invalid date for nothing", () => {
    expect(Number.isNaN(parseDate(null).getTime())).toBe(true);
  });
});
