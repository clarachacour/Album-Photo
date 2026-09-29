/**
 * Sends photos to the server in batches, built to hold up on a weak or
 * unstable connection (think Lebanese wifi) without slowing down a good one:
 *
 * - Batches of at most 8 photos / 20 MB (Cloud Run refuses requests over
 *   ~32 MB).
 * - A batch that fails because of the connection or the server is sent
 *   again, up to 5 times, waiting a little longer each time (and until the
 *   device is back online). The server skips a photo it already has, so
 *   sending a batch twice never makes duplicates.
 * - The number of batches in flight adapts: it starts at 4, goes up to 16
 *   while batches go through quickly (fast connection: as fast as before),
 *   and is halved after each failure (weak connection: requests stop
 *   competing with each other until they all time out).
 *
 * send(files, { timeout }) sends one batch and resolves to
 * { uploaded, limitReached } — or throws (an axios error, or an Error with
 * a `status`).
 *
 * Resolves to:
 *   uploaded     photos the server accepted
 *   rejected     photos the server received but couldn't use (unreadable
 *                file, unsupported format…)
 *   failedFiles  photos that never got through because of the connection
 *                or the server: can be sent again later
 *   refused      photos in batches the server refused outright (retrying
 *                wouldn't help)
 *   limitReached the album hit its photo limit; the rest wasn't sent
 *   errorDetail  the server's message for a refusal that retrying can't fix
 */

const MAX_BATCH_BYTES = 20 * 1024 * 1024;
const MAX_BATCH_COUNT = 8;

export function makeBatches(files) {
  const batches = [];
  let i = 0;
  while (i < files.length) {
    const batch = [];
    let bytes = 0;
    while (i < files.length && batch.length < MAX_BATCH_COUNT && (batch.length === 0 || bytes + files[i].size <= MAX_BATCH_BYTES)) {
      batch.push(files[i]);
      bytes += files[i].size;
      i++;
    }
    batches.push(batch);
  }
  return batches;
}

function statusOf(err) {
  return err?.response?.status ?? err?.status;
}

// No answer at all (connection lost, timeout), a server error, or "too
// many requests": worth another try. Anything else (album not found,
// already ordered, photo limit…) would fail the same way again.
export function isRetryable(err) {
  const status = statusOf(err);
  return !status || status >= 500 || status === 408 || status === 429;
}

// Long enough for a 20 MB batch on a very slow connection (~40 KB/s),
// short enough that a request stuck forever is eventually given up on.
export function batchTimeout(files) {
  const bytes = files.reduce((sum, f) => sum + f.size, 0);
  return 60_000 + Math.round(bytes / 40);
}

const defaultSleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Resolves at once when online; otherwise when the connection comes back
// (or after `maxMs`, in case the browser never says so).
function waitUntilOnline(maxMs = 60_000) {
  if (typeof navigator === "undefined" || navigator.onLine !== false) return Promise.resolve();
  return new Promise((resolve) => {
    const done = () => {
      window.removeEventListener("online", done);
      clearTimeout(timer);
      resolve();
    };
    const timer = setTimeout(done, maxMs);
    window.addEventListener("online", done);
  });
}

export async function uploadInBatches(files, send, options = {}) {
  const {
    onProgress,
    startConcurrency = 4,
    maxConcurrency = 16,
    maxAttempts = 5,
    fastMs = 15_000, // a batch this quick means the connection can take more
    sleep = defaultSleep,
    waitOnline = waitUntilOnline,
  } = options;

  const queue = makeBatches(files).map((batch) => ({ files: batch, attempts: 0 }));
  const total = files.length;
  const result = { uploaded: 0, rejected: 0, refused: 0, failedFiles: [], limitReached: false, errorDetail: null };
  let done = 0;
  let concurrency = startConcurrency;
  let active = 0;
  let finish;
  const finished = new Promise((resolve) => (finish = resolve));

  const report = () => onProgress && onProgress({ done, total });

  const pump = () => {
    if (result.limitReached) queue.length = 0; // no room left: don't send the rest
    while (active < concurrency && queue.length) run(queue.shift());
    if (active === 0 && queue.length === 0) finish();
  };

  const run = async (job) => {
    active++;
    const started = Date.now();
    try {
      const res = await send(job.files, { timeout: batchTimeout(job.files) });
      const uploaded = Math.min(job.files.length, res?.uploaded ?? job.files.length);
      result.uploaded += uploaded;
      if (res?.limitReached) result.limitReached = true;
      // Photos the server left out because the album was full aren't "unreadable".
      else result.rejected += job.files.length - uploaded;
      done += job.files.length;
      if (Date.now() - started < fastMs) concurrency = Math.min(maxConcurrency, concurrency + 1);
    } catch (err) {
      job.attempts++;
      concurrency = Math.max(1, Math.floor(concurrency / 2));
      if (isRetryable(err) && job.attempts < maxAttempts) {
        // 2 s, 4 s, 8 s, 16 s — plus a little randomness so the batches
        // that failed together don't all come back at the same moment.
        await sleep(2000 * 2 ** (job.attempts - 1) + Math.random() * 1000);
        await waitOnline();
        queue.unshift(job);
      } else {
        if (isRetryable(err)) {
          result.failedFiles.push(...job.files);
        } else {
          result.refused += job.files.length;
          if (!result.errorDetail) result.errorDetail = err?.response?.data?.detail || null;
        }
        done += job.files.length;
      }
    } finally {
      active--;
      report();
      pump();
    }
  };

  report();
  pump();
  await finished;
  return result;
}
