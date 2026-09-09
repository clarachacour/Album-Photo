import React, { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";
import { ArrowLeft } from "lucide-react";
import { computeUnitPrice } from "@/lib/pricing";

export default function OrderCheckoutPage() {
  const { albumId } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();
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
        toast.error("Failed to load this album");
      }
    })();
  }, [albumId]);

  const unitPrice = album ? computeUnitPrice(album.size || "A4", album.target_pages || 50) : 0;
  const total = unitPrice * quantity;

  const placeOrder = async (e) => {
    e.preventDefault();
    const required = ["full_name", "phone", "street", "city"];
    for (const field of required) {
      if (!address[field]?.trim()) {
        toast.error("Please fill in all required shipping fields");
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
      // first step, well before the (potentially hours-long) PDF
      // generation — so by the time this catch block can even run, the
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
        toast.error("You've already placed an order for this album.");
        nav("/orders", { replace: true });
        return;
      }
      if (status === 404 || status === 400) {
        toast.error(err?.response?.data?.detail || "Please check your album and try again.");
        return;
      }
      toast.info("This is taking a little longer than expected — check your orders, your order may already be placed.");
      nav("/orders", { replace: true });
    }
  };

  const inputClass =
    "w-full border border-[color:var(--ink)]/20 p-3 text-sm bg-white focus:border-[color:var(--ink)] focus:outline-none";

  if (!album) {
    return (
      <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
        <div className="max-w-[900px] mx-auto text-sm text-[color:var(--muted)]">Loading…</div>
      </main>
    );
  }

  if (justPlaced) {
    return (
      <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12 flex items-center justify-center">
        <div className="max-w-[500px] mx-auto text-center animate-fade-up">
          <h1 className="font-serif-display text-4xl md:text-5xl tracking-tight mb-4">Order placed.</h1>
          <p className="text-[color:var(--ink)]/70">
            Thank you — we're getting <span className="font-semibold">{album.title}</span> ready for print.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
      <div className="max-w-[1000px] mx-auto">
        <Link to={`/editor/${albumId}`} className="inline-flex items-center gap-2 text-sm text-[color:var(--muted)] hover:text-[color:var(--ink)] mb-8 transition-colors">
          <ArrowLeft size={14} /> Back to editing
        </Link>

        <div className="mb-12">
          <div className="eyebrow mb-3">Order</div>
          <h1 className="font-serif-display text-4xl md:text-5xl tracking-tight">{album.title}</h1>
        </div>

        <div className="grid md:grid-cols-[1fr_320px] gap-12">
          <form onSubmit={placeOrder} id="checkout-form" noValidate>
            <div className="eyebrow mb-6">Shipping address</div>
            <div className="grid md:grid-cols-2 gap-4 mb-4">
              <div className="md:col-span-2">
                <label className="eyebrow block mb-2">Full name *</label>
                <input className={inputClass} value={address.full_name} onChange={(e) => setAddress({ ...address, full_name: e.target.value })} required />
              </div>
              <div className="md:col-span-2">
                <label className="eyebrow block mb-2">Phone *</label>
                <input className={inputClass} value={address.phone} onChange={(e) => setAddress({ ...address, phone: e.target.value })} required />
              </div>
              <div>
                <label className="eyebrow block mb-2">Street *</label>
                <input className={inputClass} value={address.street} onChange={(e) => setAddress({ ...address, street: e.target.value })} required />
              </div>
              <div>
                <label className="eyebrow block mb-2">Building</label>
                <input className={inputClass} value={address.building} onChange={(e) => setAddress({ ...address, building: e.target.value })} />
              </div>
              <div className="md:col-span-2">
                <label className="eyebrow block mb-2">City *</label>
                <input className={inputClass} value={address.city} onChange={(e) => setAddress({ ...address, city: e.target.value })} required />
              </div>
              <div className="md:col-span-2">
                <label className="eyebrow block mb-2">Additional info (optional)</label>
                <input className={inputClass} value={address.additional_info} onChange={(e) => setAddress({ ...address, additional_info: e.target.value })} placeholder="Floor, gate code, delivery notes..." />
              </div>
            </div>
            <p className="text-xs text-[color:var(--muted)] mt-1">* Required</p>
          </form>

          <aside className="border border-[color:var(--border-soft)] p-6 h-fit">
            <div className="eyebrow mb-5">Order summary</div>
            <div className="text-sm mb-4">
              <div className="flex justify-between mb-1">
                <span className="text-[color:var(--muted)]">Format</span>
                <span>{album.size} · {album.orientation}</span>
              </div>
              <div className="flex justify-between mb-1">
                <span className="text-[color:var(--muted)]">Pages</span>
                <span>{album.pages?.length || album.target_pages} / {album.target_pages}</span>
              </div>
              {(album.pages?.length || 0) < album.target_pages && (
                <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1.5 mb-3 mt-1">
                  Your album has {album.pages?.length || 0} pages. You'll still be charged the {album.target_pages}-page price.
                </div>
              )}
              <div className="text-xs text-[color:var(--muted)] bg-[color:var(--editor-canvas)] border border-[color:var(--border-soft)] rounded px-2 py-1.5 mb-3 mt-1">
                The preview you edited is shown at reduced quality for fast loading — the book we print for you will be at full print resolution.
              </div>
              <div className="flex justify-between items-center mb-1">
                <span className="text-[color:var(--muted)]">Quantity</span>
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
                <span className="text-[color:var(--muted)]">Unit price</span>
                <span>${unitPrice.toFixed(2)}</span>
              </div>
            </div>
            <div className="flex justify-between text-base font-medium border-t border-[color:var(--border-soft)] pt-4 mb-6">
              <span>Total</span>
              <span>${total.toFixed(2)}</span>
            </div>
            <button
              type="submit"
              form="checkout-form"
              className="w-full inline-flex items-center justify-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] py-3 hover:bg-[color:var(--coral)] transition-colors text-sm font-semibold tracking-widest uppercase"
              data-testid="place-order-btn"
            >
              Place order
            </button>
            <p className="text-[11px] text-[color:var(--muted)] mt-3 leading-relaxed">
              Online payment isn't set up yet — placing an order saves it and starts preparing your album. We'll follow up to complete payment.
            </p>
          </aside>
        </div>
      </div>
    </main>
  );
}
