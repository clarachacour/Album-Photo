import { describe, expect, it } from "vitest";
import { normalizeLebanesePhone } from "@/lib/phone";

describe("Lebanese phone numbers", () => {
  it("accepts the usual ways of writing them", () => {
    expect(normalizeLebanesePhone("70 123 456")).toBe("70123456");
    expect(normalizeLebanesePhone("+961 70 123 456")).toBe("70123456");
    expect(normalizeLebanesePhone("00961-71-123456")).toBe("71123456");
    expect(normalizeLebanesePhone("03 123 456")).toBe("03123456");
    expect(normalizeLebanesePhone("+961 3 123 456")).toBe("03123456");
    expect(normalizeLebanesePhone("3 123 456")).toBe("03123456");
    expect(normalizeLebanesePhone("(01) 234-567")).toBe("01234567");
  });

  it("refuses anything else", () => {
    for (const bad of ["", "12345", "+33 6 12 34 56 78", "72 123 456", "70 123 45", "abc", "+961 70 123 4567"]) {
      expect(normalizeLebanesePhone(bad)).toBeNull();
    }
  });
});
