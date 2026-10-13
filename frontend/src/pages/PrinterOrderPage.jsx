import React, { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { API } from "@/lib/api";
import { usePageMeta } from "@/hooks/usePageMeta";

/**
 * The print shop's page, opened from the email it gets for each order
 * (send_printer_order_email on the server). No account: the link carries a
 * signed token. The links in that email point here, on the site's own
 * address, rather than at the server's (mail filters drop emails linking to
 * a hosting address), and opening the page changes nothing — mail scanners
 * open every link of an email, so the book is only marked ready by the
 * button below.
 */
export default function PrinterOrderPage() {
  usePageMeta("printer");
  const { t } = useTranslation();
  const { orderId } = useParams();
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const query = `token=${encodeURIComponent(token)}`;
  const base = `${API}/order-actions/${encodeURIComponent(orderId)}`;
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`${base}/info?${query}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(r.status === 403 ? t("printer.badLink") : t("printer.error"));
        return r.json();
      })
      .then((data) => !cancelled && setInfo(data))
      .catch((e) => !cancelled && setError(e.message || t("printer.error")));
    return () => {
      cancelled = true;
    };
  }, [base, query, t]);

  const markReady = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const r = await fetch(`${base}/ready?${query}`, { method: "POST" });
      if (!r.ok) throw new Error(t("printer.error"));
      setInfo((i) => ({ ...i, ready: true, justMarked: true }));
    } catch (e) {
      setError(e.message || t("printer.error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-[70vh] flex items-center justify-center p-8 bg-[color:var(--paper)]" data-testid="printer-order">
      <div className="w-full max-w-md text-center">
        {!info && !error && <Loader2 className="w-6 h-6 animate-spin mx-auto text-[color:var(--muted)]" />}
        {error && <p className="text-sm text-red-600 mb-6">{error}</p>}
        {info && (
          <>
            <p className="eyebrow text-[color:var(--coral)] mb-3">{t("printer.eyebrow")}</p>
            <h1 className="font-serif-display text-4xl tracking-tight mb-2">{info.order_number}</h1>
            <p className="text-[color:var(--ink)]/70 mb-1">{info.album_title}</p>
            <p className="text-sm text-[color:var(--muted)] mb-8">
              {info.size} · {info.orientation} · {t("printer.quantity", { count: info.quantity })}
            </p>
            <a
              href={`${base}/download?${query}`}
              className="flex items-center justify-center w-full bg-[color:var(--ink)] text-[color:var(--paper)] px-8 py-3 mb-4 hover:bg-[color:var(--coral)] transition-colors"
            >
              <span className="text-sm font-semibold tracking-widest uppercase">{t("printer.download")}</span>
            </a>
            {info.cancelled ? (
              <p className="text-sm text-red-600">{t("printer.cancelled")}</p>
            ) : info.ready ? (
              <p className="text-sm text-[color:var(--ink)]/80" data-testid="printer-ready-done">
                {info.justMarked ? t("printer.marked") : t("printer.alreadyReady")}
              </p>
            ) : (
              <>
                <button
                  type="button"
                  onClick={markReady}
                  disabled={busy}
                  className="flex items-center justify-center gap-2 w-full bg-[color:var(--coral)] text-[color:var(--paper)] px-8 py-3 hover:opacity-90 transition-opacity disabled:opacity-60"
                  data-testid="printer-mark-ready"
                >
                  {busy && <Loader2 className="w-4 h-4 animate-spin" />}
                  <span className="text-sm font-semibold tracking-widest uppercase">{t("printer.markReady")}</span>
                </button>
                <p className="text-xs text-[color:var(--muted)] mt-3">{t("printer.markReadyHint")}</p>
              </>
            )}
          </>
        )}
      </div>
    </main>
  );
}

/** The email's download link: straight on to the PDF. */
export function PrinterDownloadRedirect() {
  const { orderId } = useParams();
  const [params] = useSearchParams();
  useEffect(() => {
    const token = encodeURIComponent(params.get("token") || "");
    window.location.replace(`${API}/order-actions/${encodeURIComponent(orderId)}/download?token=${token}`);
  }, [orderId, params]);
  return (
    <main className="min-h-[70vh] flex items-center justify-center p-8 bg-[color:var(--paper)]">
      <Loader2 className="w-6 h-6 animate-spin text-[color:var(--muted)]" />
    </main>
  );
}
