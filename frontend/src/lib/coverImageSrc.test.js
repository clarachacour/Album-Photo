import { beforeEach, describe, expect, it } from "vitest";
import { coverItemImageSrc } from "@/lib/api";

const store = {};
beforeEach(() => {
  globalThis.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => (store[k] = v), removeItem: (k) => delete store[k] };
  store.album_token = "CURRENT";
});

describe("cover image address", () => {
  const path = "albumai/users/u1/albums/a1/cover-assets/logo.png";

  it("uses the current key, not the one saved with the album", () => {
    const saved = `https://api.example/api/cover-assets/image?path=${encodeURIComponent(path)}&auth=EXPIRED&variant=original`;
    const src = coverItemImageSrc({ image_url: saved });
    expect(src).toContain("auth=CURRENT");
    expect(src).not.toContain("EXPIRED");
    expect(src).toContain(encodeURIComponent(path));
  });

  it("prefers the stored file path when there is one", () => {
    const src = coverItemImageSrc({ storage_path: path, image_url: "https://x/api/cover-assets/image?path=old&auth=EXPIRED" });
    expect(src).toContain(encodeURIComponent(path));
    expect(src).toContain("auth=CURRENT");
  });

  it("leaves images built into templates alone", () => {
    expect(coverItemImageSrc({ image_url: "data:image/png;base64,AAAA" })).toBe("data:image/png;base64,AAAA");
    expect(coverItemImageSrc({})).toBeNull();
  });
});
