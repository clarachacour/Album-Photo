import React, { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";
import { ArrowLeft } from "lucide-react";
import { billedPageCount, computeUnitPrice } from "@/lib/pricing";

export default function OrderCheckoutPage() {
  const { albumId } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const { t } = useTranslation();
  const [album, setAlbum] = useState(null);
  const [quantity, setQuantity] = useState(1);
  const [address, setAddress] = useState({
    full_name: user?.name || "",
    phone: user?.phone || "",
    street: user?.street || "",
    building: user?.building || "",
    city: user?.city || "",
    additional_info: user?.additional_info || "",
  });
  // Shown the instant the person clicks "Place order". The POST itself
  // can take anywhere from a few minutes to a couple of hours — PDF
  // generation is awaited synchronously on the server (see backend
  // create_order), not dispatched as a background task; background
  // dispatch was tried and reverted because Cloud Run could silently kill
  // it mid-render with nothing in the logs. This screen replacing the
  // form immediately is what stops a second click *in this tab* from
  // placing a duplicate order — the actual guarantee against a duplicate
  // (a reopened tab, the back button, a reload while the first request is
  // still quietly pending) is server-side, in create_order.
  const [justPlaced, setJustPlaced] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/albums/${albumId}`);
        setAlbum(data);
        // Reopening this page for an album that's already been ordered —
        // a second tab, the back button, a reload while the first order's
        // request was still quietly pending (it can take minutes to
        // hours) — used to just show the form again, ready to place a
        // genuine duplicate order. create_order now rejects that
        // server-side regardless, but catching it here means they land on
        // their actual order instead of hitting a confusing error.
        if (data.was_ordered) {
          try {
            const { data: orders } = await api.get("/orders");
            const existing = (orders || []).find((o) => o.album_id === albumId);
            if (existing) {
              nav(`/orders/${existing.id}`, { replace: true });
              return;
            }
          } catch {
            /* fall through to showing the form; create_order's own guard still applies */
          }
        }
      } catch {
        toast.error(t("checkout.loadError"));
      }
    })();
  }, [albumId]);

  const unitPrice = album ? computeUnitPrice(album.size || "A4", billedPageCount(album) || 50) : 0;
  const total = unitPrice * quantity;

  const placeOrder = async (e) => {
    e.preventDefault();
    const required = ["full_name", "phone", "street", "city"];
    for (const field of required) {
      if (!address[field]?.trim()) {
        toast.error(t("checkout.requiredFields"));
        return;
      }
    }
    setJustPlaced(true);
    try {
      const { data } = await api.post("/orders", {
        album_id: albumId,
        quantity,
        shipping_address: address,
      });
      nav(`/orders/${data.id}`);
    } catch (err) {
      // create_order inserts the order into the database as its very
      // first step, before the PDF generation starts (queued, or run in
      // the same request without the queue) — so by the time this catch
      // block can even run, the
      // order has almost always already been created and the
      // confirmation email already sent, whatever went wrong afterwards.
      // The only genuine "nothing was created" failures are the specific,
      // known validation errors below (safe to show and let them fix on
      // the form); everything else — a dropped connection during the long
      // wait, a timeout, an unexpected server error — gets a calm message
      // and a redirect to their orders list instead of an alarming
      // "failed" toast and raw backend error text, since the real
      // technical detail is never something the customer should be
      // reading (admin has that in the logs) and the order is very likely
      // already there waiting for them.
      setJustPlaced(false);
      const status = err?.response?.status;
      if (status === 409) {
        toast.error(t("checkout.alreadyOrdered"));
        nav("/orders", { replace: true });
        return;
      }
      if (status === 404 || status === 400) {
        toast.error(err?.response?.data?.detail || t("checkout.checkAlbum"));
        return;
      }
      toast.info(t("checkout.slow"));
      nav("/orders", { replace: true });
    }
  };

  const inputClass =
    "w-full border border-[color:var(--ink)]/20 p-3 text-sm bg-white focus:border-[color:var(--ink)] focus:outline-none";

  if (!album) {
    return (
      <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
        <div className="max-w-[900px] mx-auto text-sm text-[color:var(--muted)]">{t("checkout.loading")}</div>
      </main>
    );
  }

  if (justPlaced) {
    return (
      <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12 flex items-center justify-center">
        <div className="max-w-[500px] mx-auto text-center animate-fade-up">
          <h1 className="font-serif-display text-4xl md:text-5xl tracking-tight mb-4">{t("checkout.placedTitle")}</h1>
          <p className="text-[color:var(--ink)]/70">
            <Trans i18nKey="checkout.placedBody" values={{ title: album.title }} components={{ b: <span className="font-semibold" /> }} />
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
      <div className="max-w-[1000px] mx-auto">
        <Link to={`/editor/${albumId}`} className="inline-flex items-center gap-2 text-sm text-[color:var(--muted)] hover:text-[color:var(--ink)] mb-8 transition-colors">
          <ArrowLeft size={14} /> {t("checkout.backToEditing")}
        </Link>

        <div className="mb-12">
          <div className="eyebrow mb-3">{t("checkout.eyebrow")}</div>
          <h1 className="font-serif-display text-4xl md:text-5xl tracking-tight">{album.title}</h1>
        </div>

        <div className="grid md:grid-cols-[1fr_320px] gap-12">
          <form onSubmit={placeOrder} id="checkout-form" noValidate>
            <div className="eyebrow mb-6">{t("checkout.shippingAddress")}</div>
            <div className="grid md:grid-cols-2 gap-4 mb-4">
              <div className="md:col-span-2">
                <label className="eyebrow block mb-2">{t("checkout.fullName")}</label>
                <input className={inputClass} value={address.full_name} onChange={(e) => setAddress({ ...address, full_name: e.target.value })} required />
              </div>
              <div className="md:col-span-2">
                <label className="eyebrow block mb-2">{t("checkout.phone")}</label>
                <input className={inputClass} value={address.phone} onChange={(e) => setAddress({ ...address, phone: e.target.value })} required />
              </div>
              <div>
                <label className="eyebrow block mb-2">{t("checkout.street")}</label>
                <input className={inputClass} value={address.street} onChange={(e) => setAddress({ ...address, street: e.target.value })} required />
              </div>
              <div>
                <label className="eyebrow block mb-2">{t("checkout.building")}</label>
                <input className={inputClass} value={address.building} onChange={(e) => setAddress({ ...address, building: e.target.value })} />
              </div>
              <div className="md:col-span-2">
                <label className="eyebrow block mb-2">{t("checkout.city")}</label>
                <input className={inputClass} value={address.city} onChange={(e) => setAddress({ ...address, city: e.target.value })} required />
              </div>
              <div className="md:col-span-2">
                <label className="eyebrow block mb-2">{t("checkout.additionalInfo")}</label>
                <input className={inputClass} value={address.additional_info} onChange={(e) => setAddress({ ...address, additional_info: e.target.value })} placeholder={t("checkout.additionalInfoPlaceholder")} />
              </div>
            </div>
            <p className="text-xs text-[color:var(--muted)] mt-1">{t("checkout.required")}</p>
          </form>

          <aside className="border border-[color:var(--border-soft)] p-6 h-fit">
            <div className="eyebrow mb-5">{t("checkout.summary")}</div>
            <div className="text-sm mb-4">
              <div className="flex justify-between mb-1">
                <span className="text-[color:var(--muted)]">{t("checkout.format")}</span>
                <span>{album.size} · {album.orientation === "landscape" ? t("createAlbum.format.landscapeLower") : t("createAlbum.format.portraitLower")}</span>
              </div>
              <div className="flex justify-between mb-1">
                <span className="text-[color:var(--muted)]">{t("checkout.pages")}</span>
                <span>{album.pages?.length || album.target_pages} / {album.target_pages}</span>
              </div>
              {(album.pages?.length || 0) < album.target_pages && (
                <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1.5 mb-3 mt-1">
                  {t("checkout.shortAlbum", { count: album.pages?.length || 0, target: album.target_pages })}
                </div>
              )}
              <div className="text-xs text-[color:var(--muted)] bg-[color:var(--editor-canvas)] border border-[color:var(--border-soft)] rounded px-2 py-1.5 mb-3 mt-1">
                {t("checkout.previewQuality")}
              </div>
              <div className="flex justify-between items-center mb-1">
                <span className="text-[color:var(--muted)]">{t("checkout.quantity")}</span>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={quantity}
                  onChange={(e) => setQuantity(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
                  className="w-16 border border-[color:var(--ink)]/20 p-1 text-sm text-center focus:border-[color:var(--ink)] focus:outline-none"
                />
              </div>
              <div className="flex justify-between">
                <span className="text-[color:var(--muted)]">{t("checkout.unitPrice")}</span>
                <span>${unitPrice.toFixed(2)}</span>
              </div>
            </div>
            <div className="flex justify-between text-base font-medium border-t border-[color:var(--border-soft)] pt-4 mb-6">
              <span>{t("checkout.total")}</span>
              <span>${total.toFixed(2)}</span>
            </div>
            <button
              type="submit"
              form="checkout-form"
              className="w-full inline-flex items-center justify-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] py-3 hover:bg-[color:var(--coral)] transition-colors text-sm font-semibold tracking-widest uppercase"
              data-testid="place-order-btn"
            >
              {t("checkout.placeOrder")}
            </button>
            <p className="text-[11px] text-[color:var(--muted)] mt-3 leading-relaxed">
              {t("checkout.noPayment")}
            </p>
          </aside>
        </div>
      </div>
    </main>
  );
}
