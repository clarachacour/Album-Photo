import { describe, expect, it } from "vitest";
import { findExifSegment, insertExifSegment, preparePhoto, resetOrientation, targetSize } from "@/lib/preparePhoto";

// A minimal EXIF segment: one IFD0 entry, the orientation (tag 0x0112).
function exifSegment({ little = true, orientation = 6 } = {}) {
  const tiff = [];
  const u16 = (v) => (little ? [v & 0xff, v >> 8] : [v >> 8, v & 0xff]);
  const u32 = (v) => (little ? [v & 0xff, (v >> 8) & 0xff, (v >> 16) & 0xff, v >>> 24] : [v >>> 24, (v >> 16) & 0xff, (v >> 8) & 0xff, v & 0xff]);
  tiff.push(...(little ? [0x49, 0x49] : [0x4d, 0x4d]), ...u16(42), ...u32(8));
  tiff.push(...u16(1), ...u16(0x0112), ...u16(3), ...u32(1), ...u16(orientation), 0, 0, ...u32(0));
  const payload = [0x45, 0x78, 0x69, 0x66, 0, 0, ...tiff];
  const length = payload.length + 2;
  return new Uint8Array([0xff, 0xe1, length >> 8, length & 0xff, ...payload]);
}
const jfif = [0xff, 0xe0, 0, 6, 0x4a, 0x46, 0x49, 0x46]; // APP0 "JFIF" (shortened)
const imageData = [0xff, 0xda, 0, 2, 1, 2, 3, 0xff, 0xd9];
const jpeg = (...parts) => new Uint8Array([0xff, 0xd8, ...parts.flatMap((p) => [...p])]);
const orientationOf = (segment, little = true) => new DataView(segment.buffer, segment.byteOffset).getUint16(10 + 8 + 2 + 8, little);

describe("EXIF", () => {
  it("finds the EXIF segment after the JFIF header", () => {
    const exif = exifSegment();
    expect(findExifSegment(jpeg(jfif, exif, imageData))).toEqual(exif);
  });

  it("returns null without EXIF, or for something that isn't a JPEG", () => {
    expect(findExifSegment(jpeg(jfif, imageData))).toBeNull();
    expect(findExifSegment(new Uint8Array([0x89, 0x50, 0x4e, 0x47]))).toBeNull();
  });

  it("resets the orientation to normal, in both byte orders", () => {
    for (const little of [true, false]) {
      const segment = resetOrientation(exifSegment({ little, orientation: 6 }));
      expect(orientationOf(segment, little)).toBe(1);
    }
  });

  it("puts the EXIF back into the new JPEG, after its JFIF header", () => {
    const exif = exifSegment();
    const out = insertExifSegment(jpeg(jfif, imageData), exif);
    expect([...out]).toEqual([...jpeg(jfif, exif, imageData)]);
    expect(findExifSegment(out)).toEqual(exif);
  });
});

describe("targetSize", () => {
  it("brings a 12 MP phone photo to 3600 px, still above a full A4 page at 300 dpi", () => {
    const { width, height } = targetSize(4032, 3024);
    expect(width).toBe(3600);
    expect(height).toBeGreaterThan(2480);
  });

  it("brings a 48 MP photo down the same way", () => {
    const { width, height } = targetSize(8064, 6048);
    expect(width * height).toBeLessThanOrEqual(16_000_000);
    expect(Math.min(width, height)).toBeGreaterThan(2480);
    expect(Math.max(width, height)).toBeGreaterThan(3508);
  });

  it("keeps a photo that's already small enough as is", () => {
    expect(targetSize(3000, 2000)).toEqual({ width: 3000, height: 2000 });
  });

  it("never goes over 3600 px on the long side", () => {
    expect(targetSize(9000, 1000).width).toBe(3600);
  });
});

describe("preparePhoto", () => {
  it("sends small photos and non-JPEGs as they are", async () => {
    const small = new File([new Uint8Array(1000)], "a.jpg", { type: "image/jpeg" });
    const png = new File([new Uint8Array(3 * 1024 * 1024)], "b.png", { type: "image/png" });
    expect(await preparePhoto(small)).toBe(small);
    expect(await preparePhoto(png)).toBe(png);
  });
});
