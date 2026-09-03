import React, { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { API } from "@/lib/api";
import { Upload, Check, Loader2 } from "lucide-react";

export default function MobileUpload() {
  const { token } = useParams();
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [addedCount, setAddedCount] = useState(0);
  const [uploadWarning, setUploadWarning] = useState(null);
  const fileInput = useRef();

  useEffect(() => {
    fetch(`${API}/mobile-upload/${token}/info`)
      .then((r) => {
        if (!r.ok) throw new Error();
        return r.json();
      })
      .then(setInfo)
      .catch(() => setError("This link has expired or is invalid. Ask for a new QR code."));
  }, [token]);

  const handleFiles = async (fileList) => {
    const files = Array.from(fileList).filter((f) => f.type.startsWith("image/"));
    if (files.length === 0) return;
    setUploading(true);
    setUploadWarning(null);
    // Matches the desktop upload's own batching exactly (see handleFiles in
    // PhotoUploadMethods.jsx) — this used to send fixed chunks of 6 files
    // strictly one after another, which was both slower (no concurrency at
    // all, versus desktop's 16 batches in flight at once — a meaningful
    // difference on a phone's typically slower connection) and riskier (a
    // fixed count ignores actual file size, so a handful of large modern
    // phone photos in one chunk could exceed Cloud Run's ~32MB per-request
    // limit and fail the whole chunk, which likely contributed to photos
    // going missing).
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
    const BATCH_CONCURRENCY = 16;
    let nextBatch = 0;
    let added = 0;
    let failed = 0;
    const runNext = async () => {
      while (nextBatch < batches.length) {
        const chunk = batches[nextBatch++];
        // Each batch's failure is caught here, on its own — so one bad
        // batch (a network hiccup, a bad file in that batch) never stops
        // this worker from moving on to its next batch, and never affects
        // the other concurrent workers at all.
        try {
          const form = new FormData();
          chunk.forEach((f) => form.append("files", f));
          const res = await fetch(`${API}/mobile-upload/${token}/photos`, { method: "POST", body: form });
          if (!res.ok) throw new Error();
          const data = await res.json();
          added += data.uploaded || 0;
          failed += (data.failed || 0) + Math.max(0, chunk.length - (data.uploaded || 0) - (data.failed || 0));
        } catch {
          failed += chunk.length;
        }
      }
    };
    await Promise.all(Array.from({ length: Math.min(BATCH_CONCURRENCY, batches.length) }, runNext));
    setAddedCount((c) => c + added);
    if (failed > 0) {
      setUploadWarning(
        `${added} of ${added + failed} photo${added + failed > 1 ? "s" : ""} added — ${failed} didn't make it. Try selecting the rest again.`
      );
    }
    setUploading(false);
  };

  if (error) {
    return (
      <main className="min-h-screen flex items-center justify-center p-8 bg-[color:var(--paper)] text-center">
        <p className="text-[color:var(--ink)]/70">{error}</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-8 bg-[color:var(--paper)]">
      <div className="w-full max-w-sm text-center">
        <div className="eyebrow mb-3 text-[color:var(--muted)]">
          {info ? info.album_title : "Loading…"}
        </div>
        <h1 className="font-serif-display text-4xl tracking-tight mb-3">Add your photos.</h1>
        <p className="text-[color:var(--ink)]/70 mb-10">
          Choose photos from your phone — they'll appear in your album on the computer automatically.
        </p>

        <button
          onClick={() => fileInput.current?.click()}
          disabled={uploading || !info}
          className="w-full inline-flex flex-col items-center justify-center gap-3 border-2 border-dashed border-[color:var(--ink)]/30 py-12 hover:border-[color:var(--ink)]/60 transition-colors disabled:opacity-60"
        >
          {uploading ? <Loader2 size={28} className="animate-spin" /> : <Upload size={28} />}
          <span className="text-sm font-semibold tracking-widest uppercase">
            {uploading ? "Uploading…" : "Choose photos"}
          </span>
        </button>
        <input
          ref={fileInput}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = "";
          }}
        />

        {uploadWarning && (
          <p className="mt-6 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
            {uploadWarning}
          </p>
        )}

        {addedCount > 0 && (
          <div className="mt-8 flex items-center justify-center gap-2 text-sm text-[color:var(--ink)]/80">
            <Check size={16} className="text-green-600" />
            {addedCount} photo{addedCount > 1 ? "s" : ""} added — you can add more or close this page.
          </div>
        )}
      </div>
    </main>
  );
}
