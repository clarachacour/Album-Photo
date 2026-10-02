import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { api, photoImageUrl } from "@/lib/api";
import { isImageFile } from "@/lib/imageFiles";
import { toast } from "sonner";
import MobileUploadQR from "@/components/MobileUploadQR";
import GooglePhotosImportButton from "@/components/GooglePhotosImportButton";
import { Upload, Smartphone } from "lucide-react";
import { TID } from "@/constants/testIds";
import { isMobileDevice } from "@/lib/device";
import { postBatch, uploadInBatches } from "@/lib/uploadBatches";
import { preparePhoto } from "@/lib/preparePhoto";

/**
 * The three ways to add photos to an album — drag & drop / file picker,
 * scan-to-upload from a phone, and import from Google Photos — in one
 * place, so the creation wizard and the "Add more photos" editor action
 * behave identically.
 *
 * mode="wizard": uploads land in the album's photo pool but nothing is
 *   processed yet (the wizard's own "Start AI" step handles that once).
 * mode="editor": each addition is uploaded AND immediately queued for
 *   incremental AI processing — `onProcessingStarted` is called so the
 *   caller can show its processing/progress UI.
 */
export default function PhotoUploadMethods({ albumId, mode = "wizard", photos, onPhotosChange, onProcessingStarted, beforeAlbumChange, afterMethodsRow, onImportingChange }) {
  const { t } = useTranslation();
  const [drag, setDrag] = useState(false);
  const [showQR, setShowQR] = useState(false);
  const [phoneSession, setPhoneSession] = useState(null);
  // True while the phone that scanned the QR code says it's sending photos.
  const [phoneUploading, setPhoneUploading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(null); // { done, total } while sending
  // Photos the connection didn't let through, offered to be sent again.
  const [failedFiles, setFailedFiles] = useState([]);
  const [googleImporting, setGoogleImporting] = useState(false);
  const fileInput = React.useRef();
  // Doesn't change for the lifetime of a page load, so no need for this to
  // be reactive state — just computed once. "From your phone" (scan a QR
  // code with your phone) only makes sense when the person is on a
  // *different* device than the one in front of them right now; someone
  // already on their phone tapping it would just be shown a QR code for
  // the phone they're already holding.
  const onPhone = React.useRef(isMobileDevice()).current;
  // The polling effect below only re-runs when phoneSession/albumId
  // change, not on every showQR toggle — reading showQR directly inside
  // its setInterval callback would see whatever it was when the effect
  // last (re)started, not whatever it currently is. This ref is kept in
  // sync separately so the polling loop always sees the live value.
  const showQRRef = React.useRef(showQR);
  useEffect(() => {
    showQRRef.current = showQR;
  }, [showQR]);

  // A single, method-agnostic "something is still coming in" signal —
  // device upload, phone/QR, and Google Photos each have their own
  // internal progress state, but the caller (the wizard's Photos step)
  // just needs to know whether it's safe to let the person move on yet,
  // regardless of which method is active. The phone tells the server when
  // it starts and finishes sending (see MobileUpload.jsx), so this frees
  // up as soon as the last photo is in — no guessing from a quiet spell.
  const importing = uploading || googleImporting || phoneUploading;
  useEffect(() => {
    onImportingChange && onImportingChange(importing);
  }, [importing]); // eslint-disable-line react-hooks/exhaustive-deps

  const startPhoneUpload = async () => {
    if (!albumId) return;
    setShowQR(true);
    if (phoneSession) return; // a session's already running — just re-show the modal, no new one needed
    try {
      const { data } = await api.post(`/albums/${albumId}/mobile-upload-session`);
      setPhoneSession(data);
    } catch {
      toast.error(t("photoUpload.linkError"));
    }
  };

  // Polling lives here (not inside the QR modal component) specifically so
  // closing the modal doesn't stop it — the person may well close the QR
  // code once they've started selecting photos on their phone, and photos
  // can keep landing for a while after that.
  useEffect(() => {
    if (!phoneSession) return;
    let lastCount = (photos || []).length;
    let polling = false;
    let active = true;
    let wasUploading = false;
    const doPoll = async () => {
      if (polling || !active) return;
      polling = true;
      try {
        // Status first: when it says "done", the album read right after
        // already has every photo the phone sent.
        const { data: status } = await api.get(`/albums/${albumId}/mobile-upload-session/${phoneSession.token}`);
        const { data } = await api.get(`/albums/${albumId}`);
        if (!active) return;
        if (wasUploading && !status.uploading) toast.success(t("photoUpload.phoneDone"));
        wasUploading = status.uploading;
        setPhoneUploading(status.uploading);
        const newPhotos = data.photos || [];
        if (newPhotos.length > lastCount) {
          lastCount = newPhotos.length;
          // The person is on their phone at this point, not looking at this
          // screen — closing the QR modal once photos genuinely start
          // arriving (rather than leaving it up for the full hour) gets it
          // out of the way automatically. Polling itself is untouched by
          // this (see the comment above the effect) — more photos keep
          // landing after the modal closes.
          if (showQRRef.current) {
            setShowQR(false);
            toast.success(t("photoUpload.phoneComing"));
          }
        }
        onPhotosChange(newPhotos);
        if (mode === "editor" && data.status === "processing") {
          onProcessingStarted && onProcessingStarted();
        }
      } catch {
        /* ignore transient poll errors */
      } finally {
        polling = false;
      }
    };
    const interval = setInterval(doPoll, 3000);
    // Browsers throttle setInterval heavily in a background tab — and this
    // tab is almost always backgrounded during a phone upload, since the
    // person is looking at their phone, not this screen, the whole time.
    // Without this, the 3s interval above could take a very long time to
    // actually fire again once backgrounded, leaving the QR modal open (or
    // this screen looking stale) long after photos have genuinely finished
    // landing. Firing one poll immediately the moment the tab regains
    // focus catches it up right away instead of waiting on the throttled
    // interval.
    const onVisible = () => {
      if (document.visibilityState === "visible") doPoll();
    };
    document.addEventListener("visibilitychange", onVisible);
    // Matches the upload link's own stated 1-hour validity (see
    // MobileUploadQR) — no point polling past that, the link itself will
    // have stopped accepting new uploads by then.
    const stopTimeout = setTimeout(() => {
      clearInterval(interval);
      setPhoneUploading(false);
    }, 60 * 60 * 1000);
    return () => {
      active = false;
      clearInterval(interval);
      clearTimeout(stopTimeout);
      document.removeEventListener("visibilitychange", onVisible);
      setPhoneUploading(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phoneSession, albumId]);

  const refreshAlbum = async () => {
    const { data } = await api.get(`/albums/${albumId}`);
    onPhotosChange(data.photos || []);
    return data;
  };

  const handleFiles = async (fileList) => {
    const files = Array.from(fileList).filter(isImageFile);
    if (files.length === 0 || !albumId || uploading) return;
    setUploading(true);
    setFailedFiles([]);
    setProgress({ done: 0, total: files.length });
    try {
      // The new pages go onto the saved album: edits in progress go first.
      if (mode === "editor" && beforeAlbumChange) await beforeAlbumChange();
      const endpoint = mode === "editor" ? `/albums/${albumId}/add-photos` : `/albums/${albumId}/photos`;
      // Batching, retries after a dropped connection and how many batches
      // go at once: see uploadInBatches.
      const res = await uploadInBatches(
        files,
        async (batch, { onSent }) => {
          const form = new FormData();
          // Heavy photos are made lighter first (see preparePhoto).
          (await Promise.all(batch.map(preparePhoto))).forEach((f) => form.append("files", f));
          const { data } = await postBatch(api, endpoint, form, { onSent, config: { headers: { "Content-Type": "multipart/form-data" } } });
          return { uploaded: mode === "editor" ? data?.added : data?.uploaded, limitReached: data?.limit_reached };
        },
        { onProgress: setProgress }
      );
      if (res.errorDetail) toast.error(res.errorDetail);
      if (res.limitReached) toast.warning(t("photoUpload.limitReached"), { duration: 8000 });
      if (res.rejected > 0) toast.warning(t("photoUpload.unreadable", { count: res.rejected }), { duration: 8000 });
      setFailedFiles(res.failedFiles);
      if (mode === "editor") {
        // The server has already placed them (or said the album is full):
        // show the album as it is now, like after a Google Photos import.
        if (res.uploaded > 0) {
          const data = await handlePhoneOrGoogleUpdate();
          if (data?.status !== "processing" && !(data?.unplaced_added > 0)) {
            toast.success(t("photoUpload.addedToAlbum", { count: res.uploaded }));
          }
        }
      } else {
        await refreshAlbum();
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("photoUpload.addError"));
    } finally {
      setUploading(false);
      setProgress(null);
    }
  };

  // Closing the page (or reloading it) in the middle would stop the upload.
  useEffect(() => {
    if (!uploading) return;
    const warn = (e) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [uploading]);

  const handlePhoneOrGoogleUpdate = async () => {
    const data = await refreshAlbum();
    // Still being laid out (photos arriving from another device, say):
    // the editor waits for the end before showing the pages.
    if (mode === "editor" && data.status === "processing") {
      onProcessingStarted && onProcessingStarted();
    }
    return data;
  };

  return (
    <div>
      <div
        data-testid={TID.photoDropzone}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => !uploading && fileInput.current?.click()}
        className={`border-2 border-dashed cursor-pointer p-16 text-center transition-colors ${
          drag ? "border-[color:var(--coral)] bg-[color:var(--coral)]/5" : "border-[color:var(--ink)]/20 hover:border-[color:var(--ink)]/50"
        }`}
      >
        <Upload size={32} className="mx-auto mb-4 text-[color:var(--muted)]" />
        <p className="font-serif-display text-2xl mb-2">
          {uploading ? t("photoUpload.uploading") : onPhone ? t("photoUpload.tapToChoose") : t("photoUpload.dragHere")}
        </p>
        {progress ? (
          <div className="max-w-sm mx-auto" data-testid="upload-progress">
            <div className="h-1.5 bg-[color:var(--ink)]/10 overflow-hidden">
              <div
                className="h-full bg-[color:var(--coral)] transition-all duration-300"
                style={{ width: `${progress.total ? ((progress.partial ?? progress.done) / progress.total) * 100 : 0}%` }}
              />
            </div>
            <p className="text-sm mt-3">{t("photoUpload.progress", progress)}</p>
            <p className="text-[color:var(--muted)] text-xs mt-1">{t("photoUpload.keepOpen")}</p>
          </div>
        ) : (
          <p className="text-[color:var(--muted)] text-sm">{onPhone ? t("photoUpload.cameraRoll") : t("photoUpload.clickToBrowse")}</p>
        )}
        <input
          ref={fileInput}
          data-testid={TID.photoInput}
          type="file"
          multiple
          accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
          className="hidden"
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {failedFiles.length > 0 && !uploading && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-amber-800 bg-amber-50 border border-amber-200 px-4 py-3" data-testid="upload-failed">
          <span>{t("photoUpload.failed", { count: failedFiles.length })}</span>
          <button
            type="button"
            onClick={() => handleFiles(failedFiles)}
            className="text-xs font-semibold tracking-widest uppercase underline underline-offset-4 hover:text-[color:var(--ink)]"
            data-testid="upload-resend"
          >
            {t("photoUpload.resend", { count: failedFiles.length })}
          </button>
        </div>
      )}

      <div className="mt-6 flex flex-wrap gap-3">
        {!onPhone && (
          <button
            type="button"
            onClick={startPhoneUpload}
            disabled={!albumId}
            data-testid="add-from-phone-button"
            className="inline-flex items-center justify-center gap-2 border border-[color:var(--ink)]/30 py-3 px-5 hover:border-[color:var(--ink)] transition-colors disabled:opacity-60"
          >
            <Smartphone size={16} />
            <span className="text-sm font-semibold tracking-widest uppercase">{t("photoUpload.fromPhone")}</span>
          </button>
        )}
        {albumId && <GooglePhotosImportButton albumId={albumId} onImported={handlePhoneOrGoogleUpdate} onBusyChange={setGoogleImporting} />}
      </div>

      {afterMethodsRow}

      {!onPhone && showQR && albumId && (
        <MobileUploadQR
          session={phoneSession}
          onClose={() => setShowQR(false)}
        />
      )}

      {photos && photos.length > 0 && (
        <div className="mt-10">
          <div className="eyebrow mb-4">{t("photoUpload.addedSoFar", { count: photos.length })}</div>
          <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-8 gap-2">
            {photos.map((p) => (
              <div key={p.id} className="relative aspect-square bg-[color:var(--editor-canvas)] overflow-hidden">
                <img src={photoImageUrl(p.id)} alt="" loading="lazy" decoding="async" className="w-full h-full object-cover" />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
