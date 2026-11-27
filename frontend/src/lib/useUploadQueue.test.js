import { describe, expect, it } from "vitest";
import { summarize } from "@/lib/useUploadQueue";
import { uploadInBatches } from "@/lib/uploadBatches";

const photos = (n) => Array.from({ length: n }, (_, i) => ({ name: `p${i}`, size: 1024 * 1024 }));
const fast = { sleep: () => Promise.resolve(), waitOnline: () => Promise.resolve() };
const networkError = () => Object.assign(new Error("Network Error"), { response: undefined });

describe("the upload tally", () => {
  it("counts every photo chosen once, across several rounds", async () => {
    // Round 1: all in. Round 2 (chosen during round 1): one batch never
    // gets through, one photo is unreadable.
    const first = await uploadInBatches(photos(12), async (files) => ({ uploaded: files.length }), fast);
    let call = 0;
    const second = await uploadInBatches(photos(18), async (files) => {
      call++;
      if (call === 1) throw networkError();
      if (call === 2) return { uploaded: files.length - 1 };
      return { uploaded: files.length };
    }, { ...fast, startConcurrency: 1, maxAttempts: 1 });
    const sum = summarize(30, [first, second]);
    expect(sum.checked).toBe(true);
    expect(sum.uploaded + sum.rejected + sum.notSent).toBe(30);
    expect(sum.notSent).toBe(6);
    expect(sum.rejected).toBe(1);
  });

  it("notices when the counts don't add up", () => {
    expect(summarize(10, [{ uploaded: 8, rejected: 0, refused: 0, failedFiles: [] }]).checked).toBe(false);
  });

  it("counts the photos left out once the album is full", async () => {
    const res = await uploadInBatches(photos(40), async (files) => ({ uploaded: files.length, limitReached: true }), { ...fast, startConcurrency: 1 });
    const sum = summarize(40, [res]);
    expect(sum.limitReached).toBe(true);
    expect(sum.checked).toBe(true);
    expect(sum.uploaded).toBe(6);
    expect(sum.refused).toBe(34);
  });
});
