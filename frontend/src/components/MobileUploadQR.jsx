import React, { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { api } from "@/lib/api";
import { X, Smartphone } from "lucide-react";

/**
 * Shows a QR code linked to a short-lived mobile upload session for this
 * album. Polls the album's photo count while open so newly-added phone
 * photos get picked up automatically, without the user needing to refresh.
 */
export default function MobileUploadQR({ albumId, onNewPhotos, onClose }) {
  const [session, setSession] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api
      .post(`/albums/${albumId}/mobile-upload-session`)
      .then(({ data }) => {
        if (!cancelled) setSession(data);
      })
      .catch(() => setError("Could not create an upload link — try again."));
    return () => {
      cancelled = true;
    };
  }, [albumId]);

  useEffect(() => {
    if (!session) return;
    const interval = setInterval(async () => {
      try {
        const { data } = await api.get(`/albums/${albumId}`);
        onNewPhotos && onNewPhotos(data.photos || []);
      } catch {
        /* ignore transient poll errors */
      }
    }, 3000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, albumId]);

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-6" onClick={onClose}>
      <div
        className="bg-[color:var(--paper)] max-w-sm w-full p-8 text-center relative"
        onClick={(e) => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-[color:var(--muted)] hover:text-[color:var(--ink)]" aria-label="Close">
          <X size={18} />
        </button>
        <Smartphone size={22} className="mx-auto mb-4 text-[color:var(--muted)]" />
        <h3 className="font-serif-display text-2xl tracking-tight mb-2">Scan with your phone.</h3>
        <p className="text-sm text-[color:var(--ink)]/70 mb-6">
          Open your phone's camera, scan the code, and choose your photos — they'll appear here automatically.
        </p>
        {error && <p className="text-sm text-red-600">{error}</p>}
        {session && (
          <div className="flex justify-center p-4 bg-white border border-[color:var(--border-soft)] inline-block">
            <QRCodeSVG value={session.upload_url} size={200} />
          </div>
        )}
        <p className="text-xs text-[color:var(--muted)] mt-6">This link stays active for 1 hour.</p>
      </div>
    </div>
  );
}