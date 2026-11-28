import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { QRCodeSVG } from "qrcode.react";
import { toast } from "sonner";
import { ArrowLeft, Images, Loader2, Monitor, Smartphone, X } from "lucide-react";
import { api, photoImageUrl } from "@/lib/api";
import { isImageFile } from "@/lib/imageFiles";
import { isMobileDevice } from "@/lib/device";
import GooglePhotosImportButton from "@/components/GooglePhotosImportButton";

// On a computer every image file shows in the file window (some computers
// grey out or hide files whose exact type they don't know, an iPhone HEIC
// on Windows for one; the file name is checked after). On a phone, the
// formats the server reads are listed: an iPhone then hands its photo over
// as it is.
const COMPUTER_ACCEPT = "image/*,.heic,.heif";
const PHONE_ACCEPT = "image/jpeg,image/png,image/webp,image/heic,image/heif";

const optionClass =
  "w-full inline-flex items-center gap-3 border border-ink/30 py-3 px-4 text-left hover:border-[color:var(--ink)] transition-colors disabled:opacity-60";

/**
 * Where the image for the cover comes from — the same ways as the photos
 * of the album: this device, the phone (QR code), Google Photos, or one of
 * the photos already in the album. Nothing is added to the album's photos.
 *
 * onPick(source): a File chosen on this device, or an image already stored
 * for the cover (see addCoverImage).
 */
export default function CoverImagePicker({ albumId, onPick, onClose }) {
  const { t } = useTranslation();
  const onPhone = useRef(isMobileDevice()).current;
  const fileInput = useRef(null);
  const [view, setView] = useState("menu"); // menu | phone | album
  const [busy, setBusy] = useState(false);

  const pick = (source) => {
    onPick(source);
    onClose();
  };

  // A copy made on the server (Google Photos, an album photo).
  const pickFromServer = async (request) => {
    setBusy(true);
    try {
      const { data } = await request();
      pick(data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("coverPanel.imageUploadFailed"));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return createPortal(
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onClose} data-testid="cover-image-picker">
      <div
        className="bg-[color:var(--paper)] max-w-md w-full max-h-[90vh] overflow-y-auto p-6 relative"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={t("coverPicker.title")}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-[color:var(--muted)] hover:text-[color:var(--ink)]" aria-label={t("common.close")}>
          <X size={18} />
        </button>
        {view !== "menu" && (
          <button
            type="button"
            onClick={() => setView("menu")}
            className="mb-3 inline-flex items-center gap-1 text-xs font-semibold tracking-widest uppercase text-[color:var(--muted)] hover:text-[color:var(--ink)]"
            data-testid="cover-picker-back"
          >
            <ArrowLeft size={14} /> {t("coverPicker.back")}
          </button>
        )}
        <h3 className="font-serif-display text-2xl tracking-tight mb-5 pr-6">{t("coverPicker.title")}</h3>

        {view === "menu" && (
          <div className="flex flex-col gap-2.5">
            <button type="button" className={optionClass} onClick={() => fileInput.current?.click()} disabled={busy} data-testid="cover-picker-device">
              <Monitor size={18} className="shrink-0" />
              <span className="text-sm font-semibold tracking-widest uppercase">{onPhone ? t("coverPicker.fromThisPhone") : t("coverPicker.fromComputer")}</span>
            </button>
            {!onPhone && (
              <button type="button" className={optionClass} onClick={() => setView("phone")} disabled={busy} data-testid="cover-picker-phone">
                <Smartphone size={18} className="shrink-0" />
                <span className="text-sm font-semibold tracking-widest uppercase">{t("photoUpload.fromPhone")}</span>
              </button>
            )}
            <GooglePhotosImportButton
              albumId={albumId}
              disabled={busy}
              className={optionClass}
              onPicked={(items, accessToken) => pickFromServer(() => api.post(`/albums/${albumId}/cover-assets/google-photos`, { access_token: accessToken, items }))}
            />
            <button type="button" className={optionClass} onClick={() => setView("album")} disabled={busy} data-testid="cover-picker-album">
              <Images size={18} className="shrink-0" />
              <span className="text-sm font-semibold tracking-widest uppercase">{t("coverPicker.fromAlbum")}</span>
            </button>
            {busy && (
              <p className="text-sm text-[color:var(--muted)] inline-flex items-center gap-2 mt-1">
                <Loader2 size={14} className="animate-spin" /> {t("coverPicker.preparing")}
              </p>
            )}
            <input
              ref={fileInput}
              type="file"
              accept={onPhone ? PHONE_ACCEPT : COMPUTER_ACCEPT}
              className="hidden"
              data-testid="cover-picker-file"
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = "";
                if (!f) return;
                if (!isImageFile(f)) {
                  toast.error(t("coverPicker.notAnImage"));
                  return;
                }
                pick(f);
              }}
            />
          </div>
        )}

        {view === "phone" && <PhoneView albumId={albumId} onAsset={pick} />}
        {view === "album" && (
          <AlbumPhotosView
            albumId={albumId}
            busy={busy}
            onChoose={(photoId) => pickFromServer(() => api.post(`/albums/${albumId}/cover-assets/from-photo`, { photo_id: photoId }))}
          />
        )}
      </div>
    </div>,
    document.body
  );
}

/** A QR code for the phone: the image it sends is placed on the cover. */
function PhoneView({ albumId, onAsset }) {
  const { t } = useTranslation();
  const [session, setSession] = useState(null);
  const [failed, setFailed] = useState(false);
  const [sending, setSending] = useState(false);
  const latest = useRef(onAsset);
  latest.current = onAsset;

  useEffect(() => {
    let active = true;
    api
      .post(`/albums/${albumId}/mobile-upload-session`, { purpose: "cover" })
      .then(({ data }) => active && setSession(data))
      .catch(() => active && setFailed(true));
    return () => {
      active = false;
    };
  }, [albumId]);

  useEffect(() => {
    if (!session) return undefined;
    let active = true;
    let polling = false;
    const poll = async () => {
      if (polling || !active) return;
      polling = true;
      try {
        const { data } = await api.get(`/albums/${albumId}/mobile-upload-session/${session.token}`);
        if (!active) return;
        setSending(!!data.uploading);
        const assets = data.cover_assets || [];
        if (assets.length) {
          active = false;
          latest.current(assets[assets.length - 1]);
        }
      } catch {
        /* a missed check: the next one catches up */
      } finally {
        polling = false;
      }
    };
    const timer = setInterval(poll, 2500);
    // A background tab checks rarely: once more when it's back in front.
    const onVisible = () => document.visibilityState === "visible" && poll();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      active = false;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [session, albumId]);

  return (
    <div className="text-center" data-testid="cover-picker-qr">
      <p className="text-sm text-ink/70 mb-5">{t("coverPicker.phoneInstructions")}</p>
      {failed ? (
        <p className="text-sm text-red-600">{t("mobileQr.error")}</p>
      ) : session ? (
        <div className="inline-flex justify-center p-4 bg-white border border-[color:var(--border-soft)]">
          <QRCodeSVG value={session.upload_url} size={200} />
        </div>
      ) : (
        <Loader2 size={22} className="mx-auto animate-spin text-[color:var(--muted)]" />
      )}
      <p className="text-xs text-[color:var(--muted)] mt-5 inline-flex items-center gap-2">
        {sending && <Loader2 size={12} className="animate-spin" />}
        {sending ? t("coverPicker.phoneSending") : t("coverPicker.phoneWaiting")}
      </p>
    </div>
  );
}

/** The photos already in the album (sent from this computer, the phone or Google Photos). */
function AlbumPhotosView({ albumId, busy, onChoose }) {
  const { t } = useTranslation();
  const [photos, setPhotos] = useState(null);

  useEffect(() => {
    let active = true;
    api
      .get(`/albums/${albumId}`)
      .then(({ data }) => active && setPhotos((data.photos || []).filter((p) => !p.derived_from)))
      .catch(() => active && setPhotos([]));
    return () => {
      active = false;
    };
  }, [albumId]);

  if (photos === null) return <Loader2 size={22} className="mx-auto animate-spin text-[color:var(--muted)]" />;
  if (!photos.length) return <p className="text-sm text-ink/70">{t("coverPicker.noAlbumPhotos")}</p>;
  return (
    <>
      {busy && (
        <p className="text-sm text-[color:var(--muted)] inline-flex items-center gap-2 mb-3">
          <Loader2 size={14} className="animate-spin" /> {t("coverPicker.preparing")}
        </p>
      )}
      <div className="grid grid-cols-3 sm:grid-cols-4 gap-1.5" data-testid="cover-picker-album-photos">
        {photos.map((p) => (
          <button
            key={p.id}
            type="button"
            disabled={busy}
            onClick={() => onChoose(p.id)}
            className="relative aspect-square overflow-hidden bg-[color:var(--editor-canvas)] hover:outline hover:outline-2 hover:outline-[color:var(--coral)] disabled:opacity-60"
            data-testid={`cover-picker-photo-${p.id}`}
          >
            <img src={photoImageUrl(p.id)} alt="" loading="lazy" decoding="async" className="w-full h-full object-cover" />
          </button>
        ))}
      </div>
    </>
  );
}
