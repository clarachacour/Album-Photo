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
    try {
      const chunkSize = 6;
      let added = 0;
      for (let i = 0; i < files.length; i += chunkSize) {
        const chunk = files.slice(i, i + chunkSize);
        const form = new FormData();
        chunk.forEach((f) => form.append("files", f));
        const res = await fetch(`${API}/mobile-upload/${token}/photos`, { method: "POST", body: form });
        const data = await res.json();
        added += data.uploaded || 0;
      }
      setAddedCount((c) => c + added);
    } catch {
      setError("Upload failed — check your connection and try again.");
    } finally {
      setUploading(false);
    }
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