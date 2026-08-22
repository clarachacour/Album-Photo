import React from "react";
import { QRCodeSVG } from "qrcode.react";
import { X, Smartphone } from "lucide-react";

/**
 * Shows a QR code linked to a short-lived mobile upload session for this
 * album. Purely presentational — the session itself and the polling that
 * picks up newly-added phone photos both live in the parent
 * (PhotoUploadMethods), so closing this modal (onClose) never stops an
 * upload that's still coming in from the phone; it only hides the code.
 */
export default function MobileUploadQR({ session, onClose }) {
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
          Open your phone's camera, scan the code, and choose your photos — they'll appear here automatically, even
          after you close this window.
        </p>
        {session ? (
          <div className="flex justify-center p-4 bg-white border border-[color:var(--border-soft)] inline-block">
            <QRCodeSVG value={session.upload_url} size={200} />
          </div>
        ) : (
          <p className="text-sm text-red-600">Could not create an upload link — try again.</p>
        )}
        <p className="text-xs text-[color:var(--muted)] mt-6">This link stays active for 1 hour.</p>
      </div>
    </div>
  );
}
