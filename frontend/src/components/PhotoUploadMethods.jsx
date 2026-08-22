import React, { useState, useEffect } from "react";
import { api, photoImageUrl } from "@/lib/api";
import { toast } from "sonner";
import MobileUploadQR from "@/components/MobileUploadQR";
import GooglePhotosImportButton from "@/components/GooglePhotosImportButton";
import { Upload, Smartphone } from "lucide-react";
import { TID } from "@/constants/testIds";

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
export default function PhotoUploadMethods({ albumId, mode = "wizard", photos, onPhotosChange, onProcessingStarted, afterMethodsRow, onImportingChange }) {
  const [drag, setDrag] = useState(false);
  const [showQR, setShowQR] = useState(false);
  const [phoneSession, setPhoneSession] = useState(null);
  const [phonePolling, setPhonePolling] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [googleImporting, setGoogleImporting] = useState(false);
  const fileInput = React.useRef();

  // A single, method-agnostic "something is still coming in" signal —
  // device upload, phone/QR, and Google Photos each have their own
  // internal progress state, but the caller (the wizard's Photos step)
  // just needs to know whether it's safe to let the person move on yet,
  // regardless of which method is active. phonePolling (not showQR) is
  // what actually tracks the phone upload — closing the QR modal used to
  // stop the poll entirely, silently dropping any photo the person added
  // from their phone after that point; the session and its poll now live
  // here, independent of whether the modal itself is currently visible.
  const importing = uploading || googleImporting || phonePolling;
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
      toast.error("Could not create an upload link — try again.");
    }
  };

  // Polling lives here (not inside the QR modal component) specifically so
  // closing the modal doesn't stop it — the person may well close the QR
  // code once they've started selecting photos on their phone, and photos
  // can keep landing for a while after that.
  useEffect(() => {
    if (!phoneSession) return;
    setPhonePolling(true);
    const interval = setInterval(async () => {
      try {
        const { data } = await api.get(`/albums/${albumId}`);
        onPhotosChange(data.photos || []);
        if (mode === "editor" && data.status === "processing") {
          onProcessingStarted && onProcessingStarted();
        }
      } catch {
        /* ignore transient poll errors */
      }
    }, 3000);
    // Matches the upload link's own stated 1-hour validity (see
    // MobileUploadQR) — no point polling past that, the link itself will
    // have stopped accepting new uploads by then.
    const stopTimeout = setTimeout(() => {
      clearInterval(interval);
      setPhonePolling(false);
    }, 60 * 60 * 1000);
    return () => {
      clearInterval(interval);
      clearTimeout(stopTimeout);
      setPhonePolling(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phoneSession, albumId]);

  const refreshAlbum = async () => {
    const { data } = await api.get(`/albums/${albumId}`);
    onPhotosChange(data.photos || []);
    return data;
  };

  const handleFiles = async (fileList) => {
    const files = Array.from(fileList).filter((f) => f.type.startsWith("image/"));
    if (files.length === 0 || !albumId) return;
    setUploading(true);
    try {
      const endpoint = mode === "editor" ? `/albums/${albumId}/add-photos` : `/albums/${albumId}/photos`;
      // Batch by actual size, not just file count — a handful of modern
      // phone photos can easily blow past a fixed count's assumed size.
      // Cloud Run rejects any single request over ~32MB, so keeping some
      // margin below that here avoids hitting that limit regardless of how
      // large individual photos are.
      const MAX_BATCH_BYTES = 20 * 1024 * 1024;
      const MAX_BATCH_COUNT = 8;
      const batches = [];
      let i = 0;
      while (i < files.length) {
        const chunk = [];
        let batchBytes = 0;
        while (i < files.length && chunk.length < MAX_BATCH_COUNT && (chunk.length === 0 || batchBytes + files[i].size <= MAX_BATCH_BYTES)) {
          chunk.push(files[i]);
          batchBytes += files[i].size;
          i++;
        }
        batches.push(chunk);
      }
      // Several batches in flight at once — sending them strictly one after
      // another meant a single big upload could never benefit from the
      // backend being able to handle multiple requests at the same time.
      const BATCH_CONCURRENCY = 16;
      let nextBatch = 0;
      const runNext = async () => {
        while (nextBatch < batches.length) {
          const chunk = batches[nextBatch++];
          const form = new FormData();
          chunk.forEach((f) => form.append("files", f));
          await api.post(endpoint, form, { headers: { "Content-Type": "multipart/form-data" } });
        }
      };
      await Promise.all(Array.from({ length: Math.min(BATCH_CONCURRENCY, batches.length) }, runNext));
      if (mode === "editor") {
        toast.success("Adding your new photos…");
        onProcessingStarted && onProcessingStarted();
      } else {
        await refreshAlbum();
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not add photos");
    } finally {
      setUploading(false);
    }
  };

  const handlePhoneOrGoogleUpdate = async () => {
    const data = await refreshAlbum();
    if (mode === "editor" && data.status === "processing") {
      onProcessingStarted && onProcessingStarted();
    }
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
        onClick={() => fileInput.current?.click()}
        className={`border-2 border-dashed cursor-pointer p-16 text-center transition-colors ${
          drag ? "border-[color:var(--coral)] bg-[color:var(--coral)]/5" : "border-[color:var(--ink)]/20 hover:border-[color:var(--ink)]/50"
        }`}
      >
        <Upload size={32} className="mx-auto mb-4 text-[color:var(--muted)]" />
        <p className="font-serif-display text-2xl mb-2">{uploading ? "Uploading…" : "Drag your images here"}</p>
        <p className="text-[color:var(--muted)] text-sm">or click to browse · JPG, PNG, WEBP</p>
        <input
          ref={fileInput}
          data-testid={TID.photoInput}
          type="file"
          multiple
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      <div className="mt-6 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={startPhoneUpload}
          disabled={!albumId}
          data-testid="add-from-phone-button"
          className="inline-flex items-center justify-center gap-2 border border-[color:var(--ink)]/30 py-3 px-5 hover:border-[color:var(--ink)] transition-colors disabled:opacity-60"
        >
          <Smartphone size={16} />
          <span className="text-sm font-semibold tracking-widest uppercase">From your phone</span>
        </button>
        {albumId && <GooglePhotosImportButton albumId={albumId} onImported={handlePhoneOrGoogleUpdate} onBusyChange={setGoogleImporting} />}
      </div>

      {afterMethodsRow}

      {showQR && albumId && (
        <MobileUploadQR
          session={phoneSession}
          onClose={() => setShowQR(false)}
        />
      )}

      {photos && photos.length > 0 && (
        <div className="mt-10">
          <div className="eyebrow mb-4">{photos.length} photo{photos.length > 1 ? "s" : ""} added so far</div>
          <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-8 gap-2">
            {photos.map((p) => (
              <div key={p.id} className="relative aspect-square bg-[color:var(--editor-canvas)] overflow-hidden">
                <img src={photoImageUrl(p.id)} alt="" className="w-full h-full object-cover" />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
