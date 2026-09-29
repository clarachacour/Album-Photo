/**
 * Makes a heavy photo lighter before it's sent, so an upload on a slow
 * connection takes a fraction of the time — with no loss at print time:
 *
 * - Only JPEGs above 1.5 MB are touched; anything else is sent as is.
 * - The size stays within what the server keeps anyway (5000 px on the
 *   long side, see MAX_STORED_DIMENSION_PX in the backend) and within
 *   16 million pixels (the largest canvas older iPhones can draw), which is
 *   still well above an A4 page printed at 300 dpi (3508 × 2480).
 * - Saved again as a JPEG at quality 0.92 (the server then stores it at 90,
 *   see STORED_IMAGE_QUALITY in the backend): phones save theirs at a much
 *   higher setting, which is where most of the weight goes.
 * - The EXIF data (date taken, GPS position — used to put the album in
 *   chronological order) is copied over from the original. The rotation is
 *   applied to the pixels, so the EXIF orientation is reset to "normal".
 * - The lighter version is used only if it's at least 10 % smaller; if
 *   anything goes wrong (a browser that can't decode it, not enough
 *   memory), the original is sent.
 */

const MIN_BYTES = 1.5 * 1024 * 1024;
const MAX_SIDE = 5000;
const MAX_PIXELS = 16_000_000;
const QUALITY = 0.92;
const MIN_GAIN = 0.9; // keep the lighter version only below 90 % of the original
const MAX_AT_ONCE = 2; // a decoded 12 MP photo takes ~50 MB of memory

// --- EXIF, read from and written into the JPEG bytes ---------------------

/** The EXIF segment (APP1 "Exif", marker included) of a JPEG, or null. */
export function findExifSegment(bytes) {
  if (bytes[0] !== 0xff || bytes[1] !== 0xd8) return null;
  let i = 2;
  while (i + 4 <= bytes.length && bytes[i] === 0xff) {
    const marker = bytes[i + 1];
    if (marker === 0xda || marker === 0xd9) break; // image data starts: no more headers
    const length = (bytes[i + 2] << 8) | bytes[i + 3];
    const isExif =
      marker === 0xe1 &&
      bytes[i + 4] === 0x45 && bytes[i + 5] === 0x78 && bytes[i + 6] === 0x69 && bytes[i + 7] === 0x66 && // "Exif"
      bytes[i + 8] === 0 && bytes[i + 9] === 0;
    if (isExif) return i + 2 + length <= bytes.length ? bytes.slice(i, i + 2 + length) : null;
    i += 2 + length;
  }
  return null;
}

/** Sets the orientation tag of an EXIF segment (from findExifSegment) to 1, in place. */
export function resetOrientation(segment) {
  const tiff = 10; // marker (2) + length (2) + "Exif\0\0" (6)
  const little = segment[tiff] === 0x49; // "II" = little-endian, "MM" = big-endian
  const view = new DataView(segment.buffer, segment.byteOffset, segment.byteLength);
  const u16 = (at) => view.getUint16(at, little);
  const ifd0 = tiff + view.getUint32(tiff + 4, little);
  if (ifd0 + 2 > segment.length) return segment;
  const entries = u16(ifd0);
  for (let n = 0; n < entries; n++) {
    const entry = ifd0 + 2 + n * 12;
    if (entry + 12 > segment.length) break;
    if (u16(entry) === 0x0112) view.setUint16(entry + 8, 1, little);
  }
  return segment;
}

/** The JPEG with the EXIF segment added after its first headers. */
export function insertExifSegment(jpeg, segment) {
  let at = 2; // after the start-of-image marker…
  if (jpeg[2] === 0xff && jpeg[3] === 0xe0) at = 4 + ((jpeg[4] << 8) | jpeg[5]); // …and the JFIF header, if any
  const out = new Uint8Array(jpeg.length + segment.length);
  out.set(jpeg.subarray(0, at), 0);
  out.set(segment, at);
  out.set(jpeg.subarray(at), at + segment.length);
  return out;
}

/** Width and height that fit within MAX_SIDE and MAX_PIXELS. */
export function targetSize(width, height) {
  const scale = Math.min(1, MAX_SIDE / Math.max(width, height), Math.sqrt(MAX_PIXELS / (width * height)));
  return { width: Math.floor(width * scale), height: Math.floor(height * scale) };
}

// --- Re-encoding ----------------------------------------------------------

let running = 0;
const waiting = [];
async function oneAtATime(task) {
  if (running >= MAX_AT_ONCE) await new Promise((resolve) => waiting.push(resolve));
  running++;
  try {
    return await task();
  } finally {
    running--;
    waiting.shift()?.();
  }
}

async function lighten(file) {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const { width, height } = targetSize(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  try {
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(bitmap, 0, 0, width, height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", QUALITY));
    if (!blob) return file;
    let bytes = new Uint8Array(await blob.arrayBuffer());
    // The EXIF segment is at the start of the file: no need to read all of it.
    const exif = findExifSegment(new Uint8Array(await file.slice(0, 256 * 1024).arrayBuffer()));
    if (exif) bytes = insertExifSegment(bytes, resetOrientation(exif));
    if (bytes.length >= file.size * MIN_GAIN) return file;
    const name = file.name.replace(/\.[^.]*$/, "") + ".jpg";
    return new File([bytes], name, { type: "image/jpeg", lastModified: file.lastModified });
  } finally {
    bitmap.close?.();
    canvas.width = canvas.height = 0; // frees the canvas memory right away (Safari)
  }
}

// A batch sent again reuses the version already prepared.
const prepared = new WeakMap();

/** The file to send for this photo: a lighter copy, or the original. Never fails. */
export function preparePhoto(file) {
  if (file.type !== "image/jpeg" || file.size < MIN_BYTES || typeof createImageBitmap !== "function") {
    return Promise.resolve(file);
  }
  if (!prepared.has(file)) {
    prepared.set(file, oneAtATime(() => lighten(file)).catch(() => file));
  }
  return prepared.get(file);
}
