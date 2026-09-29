import React, { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { API } from "@/lib/api";
import { Upload, Check, Loader2 } from "lucide-react";
import GooglePhotosImportButton from "@/components/GooglePhotosImportButton";
import { uploadInBatches } from "@/lib/uploadBatches";

export default function MobileUpload() {
  const { token } = useParams();
  const { t } = useTranslation();
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [googleImporting, setGoogleImporting] = useState(false);
  const [addedCount, setAddedCount] = useState(0);
  const [progress, setProgress] = useState(null); // { done, total } while sending
  // Photos the connection didn't let through, offered to be sent again.
  const [failedFiles, setFailedFiles] = useState([]);
  const [notices, setNotices] = useState([]);
  const fileInput = useRef();

  useEffect(() => {
    let cancelled = false;
    // A real "expired or invalid" answer is a 400 from the server, and is
    // final — no point retrying that. But a plain network failure (nothing
    // came back at all) gets exactly the same generic catch() treatment
    // here as an actual 400 would, which is wrong: on iPhone specifically,
    // opening this page straight from the Camera app right after scanning
    // the QR code can land while iOS is still finishing a WiFi/cellular
    // handoff, so the very first request can fail for a reason that has
    // nothing to do with the link itself. Retrying a few times before
    // giving up avoids showing "expired" for what's really just a moment
    // without connectivity — this is also why it reportedly works fine on
    // Android (whose network stack doesn't have the same brief gap on the
    // app-to-browser handoff) but not on iPhone.
    const MAX_ATTEMPTS = 5;
    const RETRY_DELAY_MS = 1000;

    const fetchInfo = (attempt) => {
      fetch(`${API}/mobile-upload/${token}/info`)
        .then(async (r) => {
          if (!r.ok) {
            if (r.status === 400) {
              const err = new Error("expired");
              err.expired = true;
              throw err;
            }
            throw new Error(`HTTP ${r.status}`);
          }
          return r.json();
        })
        .then((data) => {
          if (!cancelled) setInfo(data);
        })
        .catch((err) => {
          if (cancelled) return;
          if (err && err.expired) {
            setError(t("mobileUpload.expired"));
            return;
          }
          if (attempt < MAX_ATTEMPTS) {
            setTimeout(() => fetchInfo(attempt + 1), RETRY_DELAY_MS * attempt);
          } else {
            setError(t("mobileUpload.offline"));
          }
        });
    };

    fetchInfo(1);
    return () => {
      cancelled = true;
    };
  }, [token, t]);

  // Tell the computer while photos are being sent, and as soon as it's
  // done, so its "Create album" button unblocks right away. Repeated every
  // 20 s: if this page goes silent (phone locked, tab closed), the server
  // stops counting it as uploading after a minute.
  const sending = uploading || googleImporting;
  useEffect(() => {
    if (!info) return;
    const report = (value) =>
      fetch(`${API}/mobile-upload/${token}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ uploading: value }),
        keepalive: true,
      }).catch(() => {});
    if (!sending) {
      report(false);
      return;
    }
    report(true);
    const heartbeat = setInterval(() => report(true), 20000);
    return () => clearInterval(heartbeat);
  }, [sending, info, token]);

  const handleFiles = async (fileList) => {
    const files = Array.from(fileList).filter((f) => f.type.startsWith("image/"));
    if (files.length === 0) return;
    setUploading(true);
    setNotices([]);
    setFailedFiles([]);
    setProgress({ done: 0, total: files.length });
    // Same batching and retries as the computer upload (see uploadInBatches).
    const res = await uploadInBatches(
      files,
      async (batch, { timeout }) => {
        const form = new FormData();
        batch.forEach((f) => form.append("files", f));
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeout);
        try {
          const r = await fetch(`${API}/mobile-upload/${token}/photos`, { method: "POST", body: form, signal: controller.signal });
          if (!r.ok) {
            const detail = await r.json().then((d) => d?.detail, () => null);
            throw Object.assign(new Error(`HTTP ${r.status}`), { response: { status: r.status, data: { detail } } });
          }
          const data = await r.json();
          return { uploaded: data.uploaded || 0, limitReached: data.limit_reached };
        } finally {
          clearTimeout(timer);
        }
      },
      { onProgress: setProgress }
    );
    setAddedCount((c) => c + res.uploaded);
    setFailedFiles(res.failedFiles);
    const notices = [];
    if (res.errorDetail) notices.push(res.errorDetail);
    if (res.limitReached) notices.push(t("photoUpload.limitReached"));
    if (res.rejected > 0) notices.push(t("mobileUpload.unreadable", { count: res.rejected }));
    setNotices(notices);
    setUploading(false);
    setProgress(null);
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
          {info ? info.album_title : t("mobileUpload.loading")}
        </div>
        <h1 className="font-serif-display text-4xl tracking-tight mb-3">{t("mobileUpload.title")}</h1>
        <p className="text-[color:var(--ink)]/70 mb-10">
          {t("mobileUpload.intro")}
        </p>

        <button
          onClick={() => fileInput.current?.click()}
          disabled={uploading || googleImporting || !info}
          className="w-full inline-flex flex-col items-center justify-center gap-3 border-2 border-dashed border-[color:var(--ink)]/30 py-12 hover:border-[color:var(--ink)]/60 transition-colors disabled:opacity-60"
        >
          {uploading ? <Loader2 size={28} className="animate-spin" /> : <Upload size={28} />}
          <span className="text-sm font-semibold tracking-widest uppercase">
            {uploading ? t("mobileUpload.uploading") : t("mobileUpload.choose")}
          </span>
        </button>
        {progress && (
          <div className="mt-4" data-testid="upload-progress">
            <div className="h-1.5 bg-[color:var(--ink)]/10 overflow-hidden">
              <div
                className="h-full bg-[color:var(--coral)] transition-all duration-300"
                style={{ width: `${progress.total ? (progress.done / progress.total) * 100 : 0}%` }}
              />
            </div>
            <p className="text-sm mt-3">{t("mobileUpload.progress", progress)}</p>
            <p className="text-[color:var(--muted)] text-xs mt-1">{t("mobileUpload.keepOpen")}</p>
          </div>
        )}
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

        {info?.album_id && (
          <div className="mt-4">
            <GooglePhotosImportButton
              mobileToken={token}
              disabled={uploading || googleImporting || !info}
              onBusyChange={setGoogleImporting}
              onImported={(count) => setAddedCount((c) => c + (count || 0))}
            />
          </div>
        )}

        {failedFiles.length > 0 && !uploading && (
          <div className="mt-6 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-3" data-testid="upload-failed">
            <p>{t("mobileUpload.failed", { count: failedFiles.length })}</p>
            <button
              type="button"
              onClick={() => handleFiles(failedFiles)}
              className="mt-2 text-xs font-semibold tracking-widest uppercase underline underline-offset-4"
              data-testid="upload-resend"
            >
              {t("mobileUpload.resend", { count: failedFiles.length })}
            </button>
          </div>
        )}
        {notices.map((notice) => (
          <p key={notice} className="mt-4 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
            {notice}
          </p>
        ))}

        {addedCount > 0 && (
          <div className="mt-8 flex items-center justify-center gap-2 text-sm text-[color:var(--ink)]/80">
            <Check size={16} className="text-green-600" />
            {t("mobileUpload.added", { count: addedCount })}
          </div>
        )}
      </div>
    </main>
  );
}
