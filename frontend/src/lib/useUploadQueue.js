import { useCallback, useEffect, useRef, useState } from "react";
import { uploadInBatches } from "@/lib/uploadBatches";

/**
 * The photos chosen are sent through one queue: photos chosen while others
 * are still going are added to it (on an iPhone, choosing 100 at a time is
 * much quicker: the phone prepares each one before handing it over), and
 * sent as soon as the ones before are done.
 *
 * Nothing is lost: every photo chosen ends up counted once, as received
 * (the server answered that it has it — a photo it already had counts
 * too), unreadable (the server got it but can't use it), refused (the
 * server said no: album full, ordered…) or not sent (the connection never
 * let it through: kept in `failedFiles`, to send again). `summary` gives
 * these counts when the queue is empty, and `checked` whether they add up
 * to every photo chosen.
 *
 * While photos are being sent, the screen is kept on (Screen Wake Lock):
 * a phone that goes to sleep stops the upload.
 *
 * send(files, { onSent }) sends one batch (see uploadInBatches).
 */
export function summarize(chosen, rounds) {
  const sum = { chosen, uploaded: 0, rejected: 0, refused: 0, notSent: 0, limitReached: false, errorDetail: null };
  for (const r of rounds) {
    sum.uploaded += r.uploaded;
    sum.rejected += r.rejected;
    sum.refused += r.refused + (r.skipped || 0);
    sum.notSent += r.failedFiles.length;
    sum.limitReached = sum.limitReached || r.limitReached;
    sum.errorDetail = sum.errorDetail || r.errorDetail;
  }
  // Every photo chosen is in exactly one of the four counts.
  sum.checked = sum.uploaded + sum.rejected + sum.refused + sum.notSent === chosen;
  return sum;
}

function useWakeLock(active) {
  useEffect(() => {
    if (!active || typeof navigator === "undefined" || !navigator.wakeLock?.request) return undefined;
    let lock = null;
    let stopped = false;
    const acquire = async () => {
      try {
        if (document.visibilityState !== "visible") return;
        lock = await navigator.wakeLock.request("screen");
        if (stopped) lock.release().catch(() => {});
      } catch {
        // Refused (battery saver, an older browser): the "keep this page
        // open" note still says it.
      }
    };
    // The lock is let go whenever the page is hidden: taken again on return.
    const onVisible = () => document.visibilityState === "visible" && acquire();
    acquire();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      document.removeEventListener("visibilitychange", onVisible);
      lock?.release().catch(() => {});
    };
  }, [active]);
}

export function useUploadQueue({ send, beforeStart, onFinished }) {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(null); // { done, total, partial }
  const [failedFiles, setFailedFiles] = useState([]);
  const [summary, setSummary] = useState(null);
  const pending = useRef([]);
  const running = useRef(false);
  const total = useRef(0);
  // The latest callbacks (the queue outlives renders).
  const latest = useRef({ send, beforeStart, onFinished });
  latest.current = { send, beforeStart, onFinished };

  useWakeLock(uploading);

  const run = useCallback(async () => {
    running.current = true;
    setUploading(true);
    setSummary(null);
    const rounds = [];
    let base = 0;
    try {
      if (latest.current.beforeStart) await latest.current.beforeStart();
      while (pending.current.length) {
        const round = pending.current.splice(0, pending.current.length);
        const res = await uploadInBatches(round, (files, opts) => latest.current.send(files, opts), {
          onProgress: (p) => setProgress({ done: base + p.done, total: total.current, partial: base + (p.partial ?? p.done) }),
        });
        base += round.length;
        rounds.push(res);
        if (res.limitReached) {
          // The album is full: what's still waiting can't go in either.
          rounds.push({ uploaded: 0, rejected: 0, refused: 0, skipped: pending.current.length, failedFiles: [] });
          base += pending.current.length;
          pending.current = [];
        }
      }
    } catch (err) {
      // Not sent (a step before sending failed): kept to send again.
      const left = pending.current.splice(0, pending.current.length);
      rounds.push({ uploaded: 0, rejected: 0, refused: 0, failedFiles: left, errorDetail: err?.response?.data?.detail || null });
    }
    const chosen = total.current;
    const result = summarize(chosen, rounds);
    const notSent = rounds.flatMap((r) => r.failedFiles);
    total.current = 0;
    running.current = false;
    setFailedFiles((prev) => [...prev, ...notSent]);
    setSummary(result);
    setProgress(null);
    setUploading(false);
    if (latest.current.onFinished) await latest.current.onFinished(result);
  }, []);

  /** Adds photos to send: sent at once, or right after the ones going. Returns whether they were queued behind others. */
  const add = useCallback(
    (files) => {
      if (!files.length) return false;
      pending.current.push(...files);
      total.current += files.length;
      setProgress((p) => (p ? { ...p, total: total.current } : { done: 0, total: total.current, partial: 0 }));
      if (running.current) return true;
      run();
      return false;
    },
    [run]
  );

  /** Sends again the photos the connection didn't let through. */
  const resend = useCallback(() => {
    setFailedFiles((prev) => {
      if (prev.length) setTimeout(() => add(prev), 0);
      return [];
    });
  }, [add]);

  return { add, resend, uploading, progress, failedFiles, summary };
}
