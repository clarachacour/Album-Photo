import { describe, expect, it, vi } from "vitest";
import { photoImageUrl, rememberPhotoLinks } from "./api";

globalThis.localStorage ??= { getItem: () => "token", setItem() {}, removeItem() {} };

describe("photoImageUrl", () => {
  const later = new Date(Date.now() + 5 * 24 * 3600 * 1000).toISOString();

  it("uses the direct R2 link when there is one", () => {
    rememberPhotoLinks([{ id: "p1", urls: { thumb: "https://r2/thumb", print: "https://r2/print", expires_at: later } }]);
    expect(photoImageUrl("p1")).toBe("https://r2/thumb");
    expect(photoImageUrl("p1", "print")).toBe("https://r2/print");
  });

  it("goes through the server for a size not made yet", () => {
    expect(photoImageUrl("p1", "medium")).toContain("/api/photos/p1/image?");
  });

  it("goes through the server when the link is about to expire", () => {
    const soon = new Date(Date.now() + 10 * 60 * 1000).toISOString();
    rememberPhotoLinks([{ id: "p2", urls: { thumb: "https://r2/old", expires_at: soon } }]);
    expect(photoImageUrl("p2")).toContain("/api/photos/p2/image?");
  });

  it("goes through the server for photos it knows nothing about", () => {
    expect(photoImageUrl("unknown")).toContain("/api/photos/unknown/image?");
  });
});

describe("server address", () => {
  it("drops a trailing dot or slash Safari can't reach", async () => {
    vi.resetModules();
    vi.stubEnv("REACT_APP_BACKEND_URL", " https://everbook-backend.example.run.app./ ");
    const { API } = await import("@/lib/api");
    expect(API).toBe("https://everbook-backend.example.run.app/api");
    vi.unstubAllEnvs();
    vi.resetModules();
  });
});
