import { describe, expect, it, vi } from "vitest";
import { makeBatches, postBatch, uploadInBatches } from "@/lib/uploadBatches";

const MB = 1024 * 1024;
const photo = (name, size = MB) => ({ name, size });
const photos = (n, size) => Array.from({ length: n }, (_, i) => photo(`p${i}`, size));
// No real waiting in tests.
const fast = { sleep: () => Promise.resolve(), waitOnline: () => Promise.resolve() };
const networkError = () => Object.assign(new Error("Network Error"), { response: undefined });
const httpError = (status, detail) => Object.assign(new Error("HTTP"), { response: { status, data: { detail } } });

describe("makeBatches", () => {
  it("keeps at most 6 photos per batch", () => {
    expect(makeBatches(photos(20)).map((b) => b.length)).toEqual([6, 6, 6, 2]);
  });

  it("keeps each batch under 12 MB, even with big photos", () => {
    expect(makeBatches(photos(5, 5 * MB)).map((b) => b.length)).toEqual([2, 2, 1]);
  });

  it("sends a photo bigger than the limit on its own", () => {
    expect(makeBatches([photo("huge", 25 * MB), photo("small")]).map((b) => b.length)).toEqual([1, 1]);
  });
});

describe("uploadInBatches", () => {
  it("uploads everything and reports progress", async () => {
    const progress = [];
    const res = await uploadInBatches(photos(20), async (files) => ({ uploaded: files.length }), {
      ...fast,
      onProgress: (p) => progress.push(p.done),
    });
    expect(res).toMatchObject({ uploaded: 20, rejected: 0, failedFiles: [], limitReached: false });
    expect(progress.at(-1)).toBe(20);
  });

  it("sends a batch again after a connection failure", async () => {
    let calls = 0;
    const res = await uploadInBatches(photos(3), async (files) => {
      calls++;
      if (calls < 3) throw networkError();
      return { uploaded: files.length };
    }, fast);
    expect(calls).toBe(3);
    expect(res).toMatchObject({ uploaded: 3, failedFiles: [] });
  });

  it("gives up after 5 attempts and returns the photos to send again", async () => {
    let calls = 0;
    const files = photos(3);
    const res = await uploadInBatches(files, async () => {
      calls++;
      throw httpError(503);
    }, fast);
    expect(calls).toBe(5);
    expect(res.uploaded).toBe(0);
    expect(res.failedFiles).toEqual(files);
  });

  it("doesn't retry a refusal that would fail again, and keeps its message", async () => {
    let calls = 0;
    const res = await uploadInBatches(photos(3), async () => {
      calls++;
      throw httpError(400, "Album full");
    }, fast);
    expect(calls).toBe(1);
    expect(res.errorDetail).toBe("Album full");
    expect(res.refused).toBe(3);
    expect(res.failedFiles).toHaveLength(0);
  });

  it("counts photos the server couldn't read", async () => {
    const res = await uploadInBatches(photos(6), async (files) => ({ uploaded: files.length - 2 }), fast);
    expect(res).toMatchObject({ uploaded: 4, rejected: 2 });
  });

  it("stops sending once the album is full", async () => {
    let calls = 0;
    const res = await uploadInBatches(photos(80), async (files) => {
      calls++;
      return { uploaded: files.length, limitReached: true };
    }, { ...fast, startConcurrency: 1 });
    expect(calls).toBe(1);
    expect(res.limitReached).toBe(true);
    expect(res.rejected).toBe(0);
  });

  it("starts with 4 batches in flight and slows down after failures", async () => {
    let inFlight = 0;
    let most = 0;
    let failures = 0;
    const res = await uploadInBatches(photos(80), async (files) => {
      inFlight++;
      most = Math.max(most, inFlight);
      await new Promise((r) => setTimeout(r, 1));
      inFlight--;
      if (failures < 3) {
        failures++;
        throw networkError();
      }
      return { uploaded: files.length };
    }, { ...fast, fastMs: 0 }); // never "fast": concurrency can only go down
    expect(most).toBe(4);
    expect(res.uploaded).toBe(80);
  });

  it("goes faster while batches go through quickly", async () => {
    let inFlight = 0;
    let most = 0;
    await uploadInBatches(photos(400), async (files) => {
      inFlight++;
      most = Math.max(most, inFlight);
      await new Promise((r) => setTimeout(r, 1));
      inFlight--;
      return { uploaded: files.length };
    }, fast);
    expect(most).toBeGreaterThan(4);
    expect(most).toBeLessThanOrEqual(16);
  });
});

describe("progress while a batch is on its way", () => {
  it("moves the bar as the bytes go out, not only when a batch is done", async () => {
    const seen = [];
    await uploadInBatches(photos(6), async (files, { onSent }) => {
      onSent(0.5);
      return { uploaded: files.length };
    }, { onProgress: (p) => seen.push(p.partial) });
    expect(seen.some((v) => v > 0 && v < 6)).toBe(true);
    expect(seen.at(-1)).toBe(6);
  });
});

describe("postBatch", () => {
  it("gives up when nothing moves for a minute, not after a fixed time", async () => {
    vi.useFakeTimers();
    let aborted = false;
    const client = {
      post: (url, form, { signal, onUploadProgress }) =>
        new Promise((resolve, reject) => {
          // Slow but steady: a little more every 30 s, for 5 minutes.
          let loaded = 0;
          const tick = setInterval(() => {
            loaded += 10;
            onUploadProgress({ loaded, total: 100 });
            if (loaded >= 100) {
              clearInterval(tick);
              resolve({ data: { uploaded: 1 } });
            }
          }, 30_000);
          signal.addEventListener("abort", () => {
            aborted = true;
            clearInterval(tick);
            reject(new Error("aborted"));
          });
        }),
    };
    const slow = postBatch(client, "/x", null);
    await vi.advanceTimersByTimeAsync(300_000);
    await expect(slow).resolves.toEqual({ data: { uploaded: 1 } });
    expect(aborted).toBe(false);

    const stuck = postBatch({ post: (url, form, { signal }) => new Promise((_, reject) => signal.addEventListener("abort", () => reject(new Error("aborted")))) }, "/x", null);
    const failed = expect(stuck).rejects.toThrow("aborted");
    await vi.advanceTimersByTimeAsync(61_000);
    await failed;
    vi.useRealTimers();
  });
});
