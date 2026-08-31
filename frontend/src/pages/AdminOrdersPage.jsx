import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, adminOrderPdfUrl } from "@/lib/api";
import { toast } from "sonner";
import { Download, ExternalLink, RefreshCw } from "lucide-react";

function formatPrice(cents, currency = "eur") {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: currency.toUpperCase() }).format((cents || 0) / 100);
}

const STATUS_COLORS = {
  pending_payment: "text-[color:var(--muted)]",
  paid: "text-[color:var(--coral)]",
  processing: "text-[color:var(--coral)]",
  printing: "text-[color:var(--coral)]",
  ready_for_delivery: "text-[color:var(--coral)]",
  shipped: "text-emerald-600",
  delivered: "text-emerald-700",
  cancelled: "text-red-500",
};

// Matches ORDER_STATUS_LABELS in server.py — kept in sync manually, same
// as the pricing table used to be before it moved to a shared file.
const STATUS_LABELS = {
  pending_payment: "Payment pending",
  paid: "Payment confirmed",
  processing: "Preparing your album",
  printing: "Printing",
  ready_for_delivery: "Ready for delivery",
  shipped: "Shipped",
  delivered: "Delivered",
  cancelled: "Cancelled",
};
const ALL_STATUSES = Object.keys(STATUS_LABELS);


/**
 * Admin-only view of every order across every customer — who ordered
 * what, where it ships, and a one-click download of the exact PDF sent
 * to the printer for that order. The customer-facing /orders only ever
 * shows the logged-in person's own orders; this is the "who does
 * orders/{id}.pdf in R2 actually belong to" lookup for the person running
 * the business. The backend itself refuses this to anyone but the
 * configured admin account, regardless of what this page shows or hides.
 */
export default function AdminOrdersPage() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [updatingId, setUpdatingId] = useState(null);
  const [regeneratingId, setRegeneratingId] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/admin/orders");
        setOrders(data);
      } catch (err) {
        if (err?.response?.status === 403) {
          setForbidden(true);
        } else {
          toast.error("Failed to load orders");
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const downloadPdf = (orderId) => {
    // A plain top-level navigation (not axios/fetch) so the browser
    // follows the redirect to R2 the same way it would any normal link —
    // no CORS involved at all. The axios/blob version tried first DID
    // follow the redirect technically, but as an XHR-based fetch it still
    // subjects the redirect's *target* (R2) to CORS, and the bucket has
    // no CORS policy allowing this frontend's origin — the browser was
    // silently blocking the response from ever reaching JavaScript, which
    // surfaced as this button's generic "not ready yet" error even though
    // the PDF was genuinely ready every time.
    window.open(adminOrderPdfUrl(orderId), "_blank");
  };

  const updateStatus = async (orderId, status) => {
    setUpdatingId(orderId);
    try {
      const { data } = await api.patch(`/admin/orders/${orderId}/status`, { status });
      setOrders((prev) => prev.map((o) => (o.id === orderId ? { ...o, ...data } : o)));
      if (status === "shipped" || status === "delivered") {
        toast.success(`Customer notified — order marked ${STATUS_LABELS[status].toLowerCase()}`);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to update status");
    } finally {
      setUpdatingId(null);
    }
  };

  const regeneratePdf = async (orderId) => {
    setRegeneratingId(orderId);
    toast.info("Regenerating — this stays open until it's actually done, which can take a while for a large album");
    try {
      // Awaited directly, not polled — the backend keeps this request
      // open for the whole render now rather than returning immediately
      // (see server.py's comment on admin_regenerate_order_pdf): Cloud
      // Run can silently kill a background task once a request has
      // already responded, so the reliable version is a slower response
      // that's guaranteed to actually finish.
      const { data } = await api.post(`/admin/orders/${orderId}/regenerate-pdf`);
      setOrders((prev) => prev.map((o) => (o.id === orderId ? { ...o, ...data } : o)));
      if (data.pdf_ready) {
        toast.success("PDF regenerated — the printer has been notified");
      } else {
        toast.error("Regeneration failed again — check the Cloud Run logs");
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to regenerate PDF");
    } finally {
      setRegeneratingId(null);
    }
  };

  if (forbidden) {
    return (
      <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
        <div className="max-w-[600px] mx-auto text-center">
          <h1 className="font-serif-display text-3xl tracking-tight mb-3">Not available</h1>
          <p className="text-[color:var(--ink)]/70">This page is only visible to the account running the business.</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
      <div className="max-w-[1400px] mx-auto">
        <h1 className="font-serif-display text-4xl tracking-tight mb-8">All orders</h1>

        {loading ? (
          <p className="text-sm text-[color:var(--muted)]">Loading…</p>
        ) : orders.length === 0 ? (
          <p className="text-sm text-[color:var(--muted)]">No orders yet.</p>
        ) : (
          <div className="overflow-x-auto border border-[color:var(--border-soft)]">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left border-b border-[color:var(--border-soft)] text-xs uppercase tracking-widest text-[color:var(--muted)]">
                  <th className="p-3">Date</th>
                  <th className="p-3">Customer</th>
                  <th className="p-3">Ship to</th>
                  <th className="p-3">Album</th>
                  <th className="p-3">Format</th>
                  <th className="p-3">Qty</th>
                  <th className="p-3">Total</th>
                  <th className="p-3">Status</th>
                  <th className="p-3">PDF</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => {
                  const addr = o.shipping_address || {};
                  return (
                    <tr key={o.id} className="border-b border-[color:var(--border-soft)] align-top">
                      <td className="p-3 whitespace-nowrap text-[color:var(--ink)]/70">
                        {o.created_at ? new Date(o.created_at).toLocaleDateString() : "—"}
                      </td>
                      <td className="p-3">
                        <div className="font-medium">{addr.full_name || "—"}</div>
                        <div className="text-xs text-[color:var(--ink)]/60">{addr.phone || ""}</div>
                      </td>
                      <td className="p-3 text-[color:var(--ink)]/70">
                        {addr.street}{addr.building ? `, ${addr.building}` : ""}<br />
                        {addr.city}
                        {addr.additional_info && <div className="text-xs italic mt-0.5">{addr.additional_info}</div>}
                      </td>
                      <td className="p-3">
                        <Link to={`/orders/${o.id}`} className="hover:text-[color:var(--coral)] inline-flex items-center gap-1">
                          {o.album_title || "Album"} <ExternalLink size={12} />
                        </Link>
                      </td>
                      <td className="p-3 whitespace-nowrap">{o.size} · {o.orientation}</td>
                      <td className="p-3">{o.quantity}</td>
                      <td className="p-3 whitespace-nowrap">{formatPrice(o.total_price_cents, o.currency)}</td>
                      <td className="p-3">
                        <select
                          value={o.status}
                          disabled={updatingId === o.id}
                          onChange={(e) => updateStatus(o.id, e.target.value)}
                          className={`text-xs font-semibold uppercase tracking-widest bg-transparent border border-[color:var(--border-soft)] px-2 py-1 disabled:opacity-60 ${STATUS_COLORS[o.status] || ""}`}
                        >
                          {ALL_STATUSES.map((s) => (
                            <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                          ))}
                        </select>
                      </td>
                      <td className="p-3">
                        <div className="flex items-center gap-1.5">
                          {o.pdf_ready ? (
                            <button
                              onClick={() => downloadPdf(o.id)}
                              className="inline-flex items-center gap-1.5 text-xs border border-[color:var(--ink)]/30 px-2.5 py-1.5 hover:border-[color:var(--ink)] transition-colors"
                            >
                              <Download size={12} />
                              Download
                            </button>
                          ) : (
                            <span className="text-xs text-red-500">Failed / not ready</span>
                          )}
                          <button
                            onClick={() => regeneratePdf(o.id)}
                            disabled={regeneratingId === o.id}
                            title="Regenerate PDF — re-runs generation and re-notifies the printer, nothing needed from the customer"
                            className="inline-flex items-center gap-1.5 text-xs border border-[color:var(--ink)]/30 px-2.5 py-1.5 hover:border-[color:var(--ink)] transition-colors disabled:opacity-60"
                          >
                            <RefreshCw size={12} className={regeneratingId === o.id ? "animate-spin" : ""} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}
