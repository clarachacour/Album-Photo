import React, { useState } from "react";
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
export default function PhotoUploadMethods({ albumId, mode = "wizard", photos, onPhotosChange, onProcessingStarted }) {
  const [drag, setDrag] = useState(false);
  const [showQR, setShowQR] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInput = React.useRef();

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
      const chunkSize = 8;
      for (let i = 0; i < files.length; i += chunkSize) {
        const chunk = files.slice(i, i + chunkSize);
        const form = new FormData();
        chunk.forEach((f) => form.append("files", f));
        await api.post(endpoint, form, { headers: { "Content-Type": "multipart/form-data" } });
      }
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
          onClick={() => setShowQR(true)}
          disabled={!albumId}
          data-testid="add-from-phone-button"
          className="inline-flex items-center justify-center gap-2 border border-[color:var(--ink)]/30 py-3 px-5 hover:border-[color:var(--ink)] transition-colors disabled:opacity-60"
        >
          <Smartphone size={16} />
          <span className="text-sm font-semibold tracking-widest uppercase">From your phone</span>
        </button>
        {albumId && <GooglePhotosImportButton albumId={albumId} onImported={handlePhoneOrGoogleUpdate} />}
      </div>

      {showQR && albumId && (
        <MobileUploadQR
          albumId={albumId}
          onClose={() => setShowQR(false)}
          onNewPhotos={(updatedPhotos) => {
            onPhotosChange(updatedPhotos);
            if (mode === "editor") onProcessingStarted && onProcessingStarted();
          }}
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