import React, { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { ImageDown, Loader2 } from "lucide-react";

const GOOGLE_CLIENT_ID = process.env.REACT_APP_GOOGLE_CLIENT_ID;
const PICKER_SCOPE = "https://www.googleapis.com/auth/photospicker.mediaitems.readonly";

// A batch this size keeps each request comfortably inside Cloud Run's
// default timeout even for large originals, while still being efficient
// (not one request per photo). BATCH_CONCURRENCY is deliberately much
// lower than the 16 used for regular device uploads (see
// PhotoUploadMethods.jsx) — these downloads go through Google's own
// servers, which start dropping connections (SSLEOFError) under too much
// simultaneous load; the backend adds its own additional per-request cap
// (GOOGLE_PHOTOS_CONCURRENCY) on top of this.
const BATCH_SIZE = 20;
const BATCH_CONCURRENCY = 2;

function loadScript(src, id) {
  return new Promise((resolve, reject) => {
    if (document.getElementById(id)) return resolve();
    const script = document.createElement("script");
    script.src = src;
    script.id = id;
    script.async = true;
    script.onload = resolve;
    script.onerror = reject;
    document.body.appendChild(script);
  });
}

/**
 * "Import from Google Photos" — opens Google's own picker UI (the user
 * never shares credentials with us, only the photos they explicitly select
 * in that session), fetches the resulting selection directly, and uploads
 * it to the backend in small batches — the same active-request-per-batch
 * pattern regular device uploads already use, instead of handing the
 * backend a session_id and one giant background task to work through on
 * its own (which ran with throttled CPU once the response had been sent,
 * making large imports far slower than they needed to be).
 */
export default function GooglePhotosImportButton({ albumId, onImported, disabled, onBusyChange }) {
  const [ready, setReady] = useState(false);
  const [busy, setBusyState] = useState(false);
  // Wraps setBusy so the parent (PhotoUploadMethods) always finds out about
  // a busy-state change too — it needs this to show a single, method-
  // agnostic "Importing…" state that covers all three ways of adding
  // photos, not just this one.
  const setBusy = (value) => {
    setBusyState(value);
    onBusyChange && onBusyChange(value);
  };
  const tokenClientRef = useRef(null);

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return;
    loadScript("https://accounts.google.com/gsi/client", "google-identity-script")
      .then(() => {
        if (!window.google) return;
        tokenClientRef.current = window.google.accounts.oauth2.initTokenClient({
          client_id: GOOGLE_CLIENT_ID,
          scope: PICKER_SCOPE,
          callback: () => {}, // overridden per-call below
        });
        setReady(true);
      })
      .catch(() => {});
  }, []);

  const pollSession = async (accessToken, sessionId) => {
    for (let i = 0; i < 60; i++) {
      const res = await fetch(`https://photospicker.googleapis.com/v1/sessions/${sessionId}`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      const data = await res.json();
      if (data.mediaItemsSet) return true;
      await new Promise((r) => setTimeout(r, 2000));
    }
    return false;
  };

  const fetchAllItems = async (accessToken, sessionId) => {
    const items = [];
    let pageToken = null;
    for (let page = 0; page < 100; page++) {
      const url = new URL("https://photospicker.googleapis.com/v1/mediaItems");
      url.searchParams.set("sessionId", sessionId);
      url.searchParams.set("pageSize", "100");
      if (pageToken) url.searchParams.set("pageToken", pageToken);
      const res = await fetch(url, { headers: { Authorization: `Bearer ${accessToken}` } });
      const data = await res.json();
      items.push(...(data.mediaItems || []));
      pageToken = data.nextPageToken;
      if (!pageToken) break;
    }
    return items;
  };

  const startImport = () => {
    if (!tokenClientRef.current || busy) return;
    tokenClientRef.current.callback = async (tokenResponse) => {
      if (tokenResponse.error) {
        toast.error("Google Photos access was not granted");
        return;
      }
      const accessToken = tokenResponse.access_token;
      setBusy(true);
      try {
        const sessionRes = await fetch("https://photospicker.googleapis.com/v1/sessions", {
          method: "POST",
          headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
          body: "{}",
        });
        const session = await sessionRes.json();
        // Always a manual click-to-open, rather than trying to auto-open or
        // auto-navigate a window ourselves — that depended on timing around
        // Google's own consent flow and worked inconsistently. A button
        // click is always a trusted user gesture, so this opens reliably
        // every time, at the cost of one extra click.
        toast.info("Click below to choose your photos in Google Photos, then come back here.", {
          duration: 15000,
          action: {
            label: "Open Google Photos",
            onClick: () => window.open(session.pickerUri, "_blank", "width=500,height=700"),
          },
        });

        const done = await pollSession(accessToken, session.id);
        if (!done) {
          toast.error("Photo selection timed out");
          return;
        }

        const items = await fetchAllItems(accessToken, session.id);
        if (items.length === 0) {
          toast.error("No photos were selected");
          return;
        }

        const batches = [];
        for (let i = 0; i < items.length; i += BATCH_SIZE) {
          batches.push(items.slice(i, i + BATCH_SIZE));
        }

        toast.info(`Importing ${items.length} photo${items.length > 1 ? "s" : ""} — this can take a few minutes for a large selection.`);

        let uploaded = 0;
        let nextBatch = 0;
        const runNext = async () => {
          while (nextBatch < batches.length) {
            const batch = batches[nextBatch++];
            try {
              const { data } = await api.post(`/albums/${albumId}/import/google-photos`, {
                access_token: accessToken,
                items: batch,
              });
              uploaded += data.uploaded || 0;
            } catch {
              // one batch failing (e.g. a transient backend error) shouldn't
              // abort every other batch still in flight — the final count
              // reported to the person reflects whatever actually made it
              // through.
            }
          }
        };
        await Promise.all(Array.from({ length: Math.min(BATCH_CONCURRENCY, batches.length) }, runNext));

        const failed = items.length - uploaded;
        if (failed > 0) {
          toast.warning(`${uploaded} of ${items.length} photos imported — ${failed} failed and were skipped. You can try importing them again.`, { duration: 8000 });
        } else {
          toast.success(`${uploaded} photo${uploaded > 1 ? "s" : ""} imported from Google Photos`);
        }
        onImported && onImported();
      } catch (err) {
        toast.error(err?.response?.data?.detail || "Google Photos import failed");
      } finally {
        setBusy(false);
      }
    };
    tokenClientRef.current.requestAccessToken();
  };

  if (!GOOGLE_CLIENT_ID || !ready) return null;

  return (
    <button
      type="button"
      onClick={startImport}
      disabled={busy || disabled}
      data-testid="google-photos-import-button"
      className="inline-flex items-center justify-center gap-2 border border-[color:var(--ink)]/30 py-3 px-5 hover:border-[color:var(--ink)] transition-colors disabled:opacity-60"
    >
      {busy ? <Loader2 size={16} className="animate-spin" /> : <ImageDown size={16} />}
      <span className="text-sm font-semibold tracking-widest uppercase">
        {busy ? "Importing…" : "From Google Photos"}
      </span>
    </button>
  );
}
