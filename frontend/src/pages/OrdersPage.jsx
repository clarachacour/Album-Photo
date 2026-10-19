import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { amountDueCents } from "@/lib/pricing";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Download, Gift, Package } from "lucide-react";
import { parseDate } from "@/lib/dates";
import { usePageMeta } from "@/hooks/usePageMeta";

function formatPrice(cents, currency = "usd") {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: currency.toUpperCase() }).format((cents || 0) / 100);
}

const STATUS_COLORS = {
  pending_payment: "text-[color:var(--muted)]",
  paid: "text-[color:var(--coral)]",
  processing: "text-[color:var(--coral)]",
  printing: "text-[color:var(--coral)]",
  shipped: "text-emerald-600",
  delivered: "text-emerald-700",
  available: "text-emerald-700",
  cancelled: "text-red-500",
};

export default function OrdersPage() {
  usePageMeta("orders");
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const { t, i18n } = useTranslation();
  // Gift cards bought, and the credit from gift cards received.
  const [giftCards, setGiftCards] = useState([]);
  const [credit, setCredit] = useState(null);

  useEffect(() => {
    api.get("/gift-cards").then(({ data }) => setGiftCards(data || [])).catch(() => {});
    api.get("/credits").then(({ data }) => setCredit(data)).catch(() => {});
  }, []);

  const downloadCard = async (card) => {
    try {
      const { data } = await api.get(`/gift-cards/${card.id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Everbook gift card ${card.code}.pdf`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      toast.error(t("orders.gifts.downloadError"));
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/orders");
        setOrders(data);
      } catch {
        toast.error(t("orders.loadError"));
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
      <div className="max-w-[1100px] mx-auto">
        <div className="mb-12">
          <div className="eyebrow mb-3">{t("orders.eyebrow")}</div>
          <h1 className="font-serif-display text-5xl md:text-6xl tracking-tight">{t("orders.title")}</h1>
        </div>

        {loading ? (
          <div className="text-sm text-[color:var(--muted)]">{t("orders.loading")}</div>
        ) : orders.length === 0 && !giftCards.length ? (
          <div className="border border-[color:var(--border-soft)] p-16 text-center">
            <Package size={28} className="mx-auto mb-4 text-[color:var(--muted)]" />
            <p className="text-sm text-[color:var(--muted)] mb-6">{t("orders.empty")}</p>
            <Link
              to="/dashboard"
              className="inline-flex items-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] px-6 py-3 hover:bg-[color:var(--coral)] transition-colors text-sm font-semibold tracking-widest uppercase"
            >
              {t("orders.goToAlbums")}
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
                    {o.kind === "digital"
                      ? `${t("checkout.kind.digital")} · ${o.size} · ${o.orientation}`
                      : `${o.size} · ${o.orientation} · ${t("orders.qty")} ${o.quantity}`}{" "}
                    · {parseDate(o.created_at).toLocaleDateString(i18n.language)}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-sm font-medium">{amountDueCents(o) > 0 ? formatPrice(amountDueCents(o), o.currency) : t("checkout.free")}</div>
                  <div className={`text-xs uppercase tracking-widest font-semibold ${STATUS_COLORS[o.status] || ""}`}>
                    {t(`orders.status.${o.status}`, { defaultValue: o.status.replace(/_/g, " ") })}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}

        {credit?.balance_cents > 0 && (
          <section className="mt-16 border border-[color:var(--coral)]/40 bg-[color:var(--coral)]/5 p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4" data-testid="orders-credit">
            <div>
              <div className="eyebrow mb-1">{t("orders.credit.title")}</div>
              <p className="text-2xl font-medium">{formatPrice(credit.balance_cents)}</p>
              <p className="text-xs text-[color:var(--muted)] mt-1">
                {t("orders.credit.until", { date: parseDate(credit.credits[0].expires_at).toLocaleDateString(i18n.language) })}
              </p>
            </div>
            <Link to="/choose-template" className="inline-block bg-[color:var(--ink)] text-[color:var(--paper)] px-6 py-3 text-sm font-semibold tracking-widest uppercase hover:bg-[color:var(--coral)] transition-colors">
              {t("orders.credit.create")}
            </Link>
          </section>
        )}

        {giftCards.length > 0 && (
          <section className="mt-16" data-testid="orders-gift-cards">
            <div className="eyebrow mb-4">{t("orders.gifts.title")}</div>
            <div className="border-t border-[color:var(--border-soft)]">
              {giftCards.map((card) => (
                <div key={card.id} className="flex items-center justify-between gap-4 py-5 border-b border-[color:var(--border-soft)]">
                  <div className="flex items-center gap-4 min-w-0">
                    <Gift size={18} className="text-[color:var(--coral)] shrink-0" />
                    <div className="min-w-0">
                      <p className="font-medium truncate">{t("cart.gift.title", { name: card.recipient_name || "…" })}</p>
                      <p className="text-xs text-[color:var(--muted)]">
                        <span className="font-mono tracking-wider text-[color:var(--ink)]">{card.code}</span> · {t("cart.gift.detail", { size: card.size, pages: card.page_tier })}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 shrink-0">
                    <span className="text-xs uppercase tracking-widest font-semibold text-[color:var(--muted)]">{t(`orders.gifts.status.${card.status}`)}</span>
                    <button type="button" onClick={() => downloadCard(card)} className="inline-flex items-center gap-1.5 text-xs underline hover:text-[color:var(--coral)]" data-testid={`gift-card-pdf-${card.code}`}>
                      <Download size={12} /> PDF
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
