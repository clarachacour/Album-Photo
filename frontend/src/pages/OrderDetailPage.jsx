import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Check, ArrowLeft } from "lucide-react";

function formatPrice(cents, currency = "eur") {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: currency.toUpperCase() }).format((cents || 0) / 100);
}

export default function OrderDetailPage() {
  const { id } = useParams();
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/orders/${id}`);
        setOrder(data);
      } catch {
        toast.error("Failed to load this order");
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  if (loading) {
    return (
      <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
        <div className="max-w-[900px] mx-auto text-sm text-[color:var(--muted)]">Loading…</div>
      </main>
    );
  }
  if (!order) return null;

  const addr = order.shipping_address || {};

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
      <div className="max-w-[900px] mx-auto">
        <Link to="/orders" className="inline-flex items-center gap-2 text-sm text-[color:var(--muted)] hover:text-[color:var(--ink)] mb-8 transition-colors">
          <ArrowLeft size={14} /> Back to your orders
        </Link>

        <div className="mb-12">
          <div className="eyebrow mb-3">Order #{order.id.slice(0, 8)}</div>
          <h1 className="font-serif-display text-4xl md:text-5xl tracking-tight">{order.album_title}</h1>
        </div>

        {order.status === "pending_payment" && (
          <div className="border border-[color:var(--coral)]/40 bg-[color:var(--coral)]/5 p-5 mb-10 text-sm">
            Payment isn't set up yet on our end — we've saved your order and started preparing your album. We'll follow up with you directly to complete payment.
          </div>
        )}

        {/* Tracking timeline */}
        <div className="mb-16">
          <div className="eyebrow mb-6">Status</div>
          {order.status === "cancelled" ? (
            <div className="text-sm text-red-500 font-medium">This order was cancelled.</div>
          ) : (
            <div className="flex flex-col gap-0">
              {order.timeline.map((step, i) => (
                <div key={step.status} className="flex items-start gap-4">
                  <div className="flex flex-col items-center">
                    <div
                      className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 ${
                        step.done ? "bg-[color:var(--ink)] text-[color:var(--paper)]" : "border border-[color:var(--ink)]/25 text-transparent"
                      }`}
                    >
                      <Check size={13} />
                    </div>
                    {i < order.timeline.length - 1 && (
                      <div className={`w-px flex-1 min-h-[28px] ${step.done ? "bg-[color:var(--ink)]" : "bg-[color:var(--ink)]/15"}`} />
                    )}
                  </div>
                  <div className={`pb-7 text-sm ${step.done ? "font-medium text-[color:var(--ink)]" : "text-[color:var(--muted)]"}`}>
                    {step.label}
                  </div>
                </div>
              ))}
            </div>
          )}
          {order.tracking_number && (
            <div className="text-sm mt-2">
              Tracking number: <span className="font-medium">{order.tracking_number}</span>
            </div>
          )}
        </div>

        <div className="grid md:grid-cols-2 gap-12 border-t border-[color:var(--border-soft)] pt-10">
          <div>
            <div className="eyebrow mb-4">Order details</div>
            <div className="text-sm space-y-1 text-[color:var(--ink)]/80">
              <div>Format: {order.size} · {order.orientation}</div>
              <div>Quantity: {order.quantity}</div>
              <div>Unit price: {formatPrice(order.unit_price_cents, order.currency)}</div>
              <div className="font-medium text-[color:var(--ink)] pt-1">Total: {formatPrice(order.total_price_cents, order.currency)}</div>
              <div className="pt-2 text-[color:var(--muted)]">Placed on {new Date(order.created_at).toLocaleDateString()}</div>
            </div>
          </div>
          <div>
            <div className="eyebrow mb-4">Shipping to</div>
            <div className="text-sm space-y-1 text-[color:var(--ink)]/80">
              <div>{addr.full_name}</div>
              <div>{addr.address_line1}</div>
              {addr.address_line2 && <div>{addr.address_line2}</div>}
              <div>{addr.postal_code} {addr.city}</div>
              <div>{addr.country}</div>
              {addr.phone && <div className="pt-1">{addr.phone}</div>}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}