/**
 * Sends photos to the server in batches, built to hold up on a weak or
 * unstable connection (think Lebanese wifi) without slowing down a good one:
 *
 * - Batches of at most 6 photos / 12 MB (Cloud Run refuses requests over
 *   ~32 MB; a smaller batch also costs less to send again).
 * - A batch that fails because of the connection or the server is sent
 *   again, up to 5 times, waiting a little longer each time (and until the
 *   device is back online). The server skips a photo it already has, so
 *   sending a batch twice never makes duplicates.
 * - The number of batches in flight adapts: it starts at 4, goes up to 16
 *   while batches go through quickly (fast connection: as fast as before),
 *   and is halved after each failure (weak connection: requests stop
 *   competing with each other until they all time out).
 *
 * - A batch is given up on only when nothing moves for a minute (see
 *   postBatch), not after a fixed time: on a phone's slow upload, several
 *   batches sharing the connection can each take many minutes and still be
 *   going fine.
 *
 * send(files, { onSent }) sends one batch — calling onSent(fraction) as its
 * bytes go out, for the progress bar — and resolves to
 * { uploaded, limitReached }, or throws (an axios error, or an Error with
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

const MAX_BATCH_BYTES = 12 * 1024 * 1024;
const MAX_BATCH_COUNT = 6;

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

const STALL_MS = 60_000; // no byte sent for this long: the connection is gone
const PROCESSING_MS = 180_000; // all sent: time left for the server to store the photos

/**
 * Posts one batch with `client` (an axios instance). Aborted when no byte
 * has gone out for STALL_MS, or the server hasn't answered PROCESSING_MS
 * after the last one — however long a slow but working upload takes.
 */
export async function postBatch(client, url, form, { onSent, config = {} } = {}) {
  const controller = new AbortController();
  let timer;
  const arm = (ms) => {
    clearTimeout(timer);
    timer = setTimeout(() => controller.abort(), ms);
  };
  arm(STALL_MS);
  try {
    return await client.post(url, form, {
      ...config,
      signal: controller.signal,
      onUploadProgress: (e) => {
        const fraction = e.total ? Math.min(1, e.loaded / e.total) : 0;
        if (onSent) onSent(fraction);
        arm(fraction >= 1 ? PROCESSING_MS : STALL_MS);
      },
    });
  } finally {
    clearTimeout(timer);
  }
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

  // Batches on their way: how much of each has gone out (0 to 1).
  const sending = new Map();
  const report = () => {
    if (!onProgress) return;
    let partial = done;
    for (const [job, fraction] of sending) partial += job.files.length * fraction * 0.95; // the rest once stored
    onProgress({ done, total, partial: Math.min(total, partial) });
  };

  const pump = () => {
    if (result.limitReached) queue.length = 0; // no room left: don't send the rest
    while (active < concurrency && queue.length) run(queue.shift());
    if (active === 0 && queue.length === 0) finish();
  };

  const run = async (job) => {
    active++;
    const started = Date.now();
    try {
      sending.set(job, 0);
      const res = await send(job.files, {
        onSent: (fraction) => {
          sending.set(job, fraction);
          report();
        },
      });
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
      sending.delete(job);
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
