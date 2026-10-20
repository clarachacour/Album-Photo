import React, { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { API } from "@/lib/api";
import { usePageMeta } from "@/hooks/usePageMeta";

/**
 * The print shop's page, opened from the email it gets for each order (or
 * for a customer's albums ordered together: one package, one click)
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
  // Several albums for one customer, packed and delivered together.
  const group = info?.albums?.length > 1;

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
      const data = await r.json().catch(() => ({}));
      setInfo((i) => ({ ...i, ready: true, justMarked: true, package_number: data.package_number, package_number_from: data.package_number_from }));
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
            {group ? (
              <>
                <p className="eyebrow text-[color:var(--coral)] mb-3">{t("printer.eyebrow")}</p>
                <h1 className="font-serif-display text-4xl tracking-tight mb-1">{t("printer.groupEyebrow", { count: info.albums.length })}</h1>
                {/* Our reference, small: the number written on the package
                    is Wakilni's, shown once the books are marked ready. */}
                <p className="text-xs text-[color:var(--muted)] mb-3">{t("printer.reference", { number: info.order_number })}</p>
                <p className="text-sm text-[color:var(--ink)]/70 mb-6">{t(info.ready ? "printer.groupHintReady" : "printer.groupHint")}</p>
                {/* Each album with its own PDF. */}
                <ol className="text-left mb-8 divide-y divide-[color:var(--ink)]/10 border-y border-[color:var(--ink)]/10" data-testid="printer-group">
                  {info.albums.map((a, i) => (
                    <li key={a.order_id} className="py-3 flex items-center justify-between gap-4">
                      <div className="min-w-0">
                        <p className="font-medium truncate">{i + 1}. {a.album_title}</p>
                        <p className="text-xs text-[color:var(--muted)]">
                          {a.order_number} · {a.size} · {a.orientation} · {t("printer.quantity", { count: a.quantity })}
                        </p>
                      </div>
                      <a
                        href={`${API}/order-actions/${encodeURIComponent(a.order_id)}/download?token=${encodeURIComponent(a.download_token)}`}
                        className="shrink-0 text-xs font-semibold tracking-widest uppercase bg-[color:var(--ink)] text-[color:var(--paper)] px-3 py-2 hover:bg-[color:var(--coral)] transition-colors"
                      >
                        PDF
                      </a>
                    </li>
                  ))}
                </ol>
              </>
            ) : (
              <>
                <p className="eyebrow text-[color:var(--coral)] mb-3">{t("printer.eyebrow")}</p>
                <h1 className="font-serif-display text-4xl tracking-tight mb-1">{info.album_title}</h1>
                <p className="text-xs text-[color:var(--muted)] mb-2">{t("printer.reference", { number: info.order_number })}</p>
                <p className="text-sm text-[color:var(--muted)] mb-8">
                  {info.size} · {info.orientation} · {t("printer.quantity", { count: info.quantity })}
                </p>
                <a
                  href={`${base}/download?${query}`}
                  className="flex items-center justify-center w-full bg-[color:var(--ink)] text-[color:var(--paper)] px-8 py-3 mb-4 hover:bg-[color:var(--coral)] transition-colors"
                >
                  <span className="text-sm font-semibold tracking-widest uppercase">{t("printer.download")}</span>
                </a>
              </>
            )}
            {info.cancelled ? (
              <p className="text-sm text-red-600">{t("printer.cancelled")}</p>
            ) : info.ready ? (
              <>
                {/* The number to write on the package: Wakilni's order
                    number, which only exists once the book is marked ready. */}
                {info.package_number && (
                  <div className="border-2 border-[color:var(--ink)] bg-white px-6 py-6 mb-6" data-testid="printer-package-number">
                    <p className="eyebrow mb-3">{t("printer.writeNumber")}</p>
                    <p className="font-mono text-5xl sm:text-6xl font-bold tracking-wider break-all">{info.package_number}</p>
                    <p className="text-xs text-[color:var(--muted)] mt-3">
                      {t(info.package_number_from === "wakilni" ? "printer.writeNumberHint" : "printer.writeNumberFallback")}
                    </p>
                  </div>
                )}
                <p className="text-sm text-[color:var(--ink)]/80" data-testid="printer-ready-done">
                  {info.justMarked ? t(group ? "printer.allMarked" : "printer.marked") : t(group ? "printer.allAlreadyReady" : "printer.alreadyReady")}
                </p>
              </>
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
                  <span className="text-sm font-semibold tracking-widest uppercase">{t(group ? "printer.markAllReady" : "printer.markReady")}</span>
                </button>
                <p className="text-xs text-[color:var(--muted)] mt-3">{t(group ? "printer.markAllReadyHint" : "printer.markReadyHint")}</p>
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

/** The printer's statement link (sent once, on the site's address): straight on to the Excel file. */
export function PrinterStatementRedirect() {
  const [params] = useSearchParams();
  useEffect(() => {
    const key = encodeURIComponent(params.get("key") || "");
    window.location.replace(`${API}/printer-statement.xlsx?key=${key}`);
  }, [params]);
  return (
    <main className="min-h-[70vh] flex items-center justify-center p-8 bg-[color:var(--paper)]">
      <Loader2 className="w-6 h-6 animate-spin text-[color:var(--muted)]" />
    </main>
  );
}
