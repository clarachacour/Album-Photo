import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Package } from "lucide-react";

function formatPrice(cents, currency = "eur") {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: currency.toUpperCase() }).format((cents || 0) / 100);
}

const STATUS_COLORS = {
  pending_payment: "text-[color:var(--muted)]",
  paid: "text-[color:var(--coral)]",
  processing: "text-[color:var(--coral)]",
  printing: "text-[color:var(--coral)]",
  shipped: "text-emerald-600",
  delivered: "text-emerald-700",
  cancelled: "text-red-500",
};

export default function OrdersPage() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/orders");
        setOrders(data);
      } catch {
        toast.error("Failed to load your orders");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
      <div className="max-w-[1100px] mx-auto">
        <div className="mb-12">
          <div className="eyebrow mb-3">Account</div>
          <h1 className="font-serif-display text-5xl md:text-6xl tracking-tight">Your orders</h1>
        </div>

        {loading ? (
          <div className="text-sm text-[color:var(--muted)]">Loading…</div>
        ) : orders.length === 0 ? (
          <div className="border border-[color:var(--border-soft)] p-16 text-center">
            <Package size={28} className="mx-auto mb-4 text-[color:var(--muted)]" />
            <p className="text-sm text-[color:var(--muted)] mb-6">You haven't ordered any albums yet.</p>
            <Link
              to="/dashboard"
              className="inline-flex items-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] px-6 py-3 hover:bg-[color:var(--coral)] transition-colors text-sm font-semibold tracking-widest uppercase"
            >
              Go to your albums
            </Link>
          </div>
        ) : (
          <div className="divide-y divide-[color:var(--border-soft)] border-t border-b border-[color:var(--border-soft)]">
            {orders.map((o) => (
              <Link
                key={o.id}
                to={`/orders/${o.id}`}
                className="flex items-center justify-between gap-6 py-6 hover:bg-black/[0.02] transition-colors px-2"
                data-testid={`order-row-${o.id}`}
              >
                <div>
                  <div className="font-serif-display text-xl tracking-tight mb-1">{o.album_title}</div>
                  <div className="text-xs text-[color:var(--muted)]">
                    {o.size} · {o.orientation} · Qty {o.quantity} · {new Date(o.created_at).toLocaleDateString()}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-sm font-medium">{formatPrice(o.total_price_cents, o.currency)}</div>
                  <div className={`text-xs uppercase tracking-widest font-semibold ${STATUS_COLORS[o.status] || ""}`}>
                    {o.status.replace(/_/g, " ")}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}