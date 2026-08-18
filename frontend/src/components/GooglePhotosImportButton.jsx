import React, { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { ImageDown, Loader2 } from "lucide-react";

const GOOGLE_CLIENT_ID = process.env.REACT_APP_GOOGLE_CLIENT_ID;
const PICKER_SCOPE = "https://www.googleapis.com/auth/photospicker.mediaitems.readonly";

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
 * in that session), then hands the session off to the backend to fetch
 * and store the chosen photos.
 */
export default function GooglePhotosImportButton({ albumId, onImported, disabled }) {
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
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
        // The backend now processes the import in the background (large
        // selections — hundreds of photos — used to time out trying to
        // finish inside one HTTP request), so this call returns almost
        // immediately and we poll the album's status instead of waiting
        // on the response body for the real result.
        await api.post(`/albums/${albumId}/import/google-photos`, {
          access_token: accessToken,
          session_id: session.id,
        });
        toast.info("Importing your photos — this can take a few minutes for a large selection.");
        for (let i = 0; i < 240; i++) {
          await new Promise((r) => setTimeout(r, 2500));
          try {
            const { data } = await api.get(`/albums/${albumId}/status`);
            if (data.status !== "processing") {
              if (data.status === "error") {
                toast.error("Google Photos import failed");
              } else {
                toast.success("Photos imported from Google Photos");
              }
              break;
            }
          } catch {
            /* keep polling — a transient network hiccup shouldn't abort the whole import */
          }
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
