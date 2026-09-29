import { describe, expect, it } from "vitest";
import { makeBatches, uploadInBatches } from "@/lib/uploadBatches";

const MB = 1024 * 1024;
const photo = (name, size = MB) => ({ name, size });
const photos = (n, size) => Array.from({ length: n }, (_, i) => photo(`p${i}`, size));
// No real waiting in tests.
const fast = { sleep: () => Promise.resolve(), waitOnline: () => Promise.resolve() };
const networkError = () => Object.assign(new Error("Network Error"), { response: undefined });
const httpError = (status, detail) => Object.assign(new Error("HTTP"), { response: { status, data: { detail } } });

describe("makeBatches", () => {
  it("keeps at most 8 photos per batch", () => {
    expect(makeBatches(photos(20)).map((b) => b.length)).toEqual([8, 8, 4]);
  });

  it("keeps each batch under 20 MB, even with big photos", () => {
    expect(makeBatches(photos(5, 7 * MB)).map((b) => b.length)).toEqual([2, 2, 1]);
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
    const res = await uploadInBatches(photos(8), async (files) => ({ uploaded: files.length - 2 }), fast);
    expect(res).toMatchObject({ uploaded: 6, rejected: 2 });
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
