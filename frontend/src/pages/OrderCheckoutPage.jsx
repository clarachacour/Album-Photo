import React, { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";
import { ArrowLeft, Loader2 } from "lucide-react";

// Kept in sync with the backend's ORDER_PRICE_CENTS — shown here only for
// the live summary as the user picks a quantity; the backend always
// recomputes and owns the real charged price.
const PRICE_TABLE = { A5: 29, A4: 39, A3: 59 };

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
  const [placing, setPlacing] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/albums/${albumId}`);
        setAlbum(data);
      } catch {
        toast.error("Failed to load this album");
      }
    })();
  }, [albumId]);

  const unitPrice = album ? PRICE_TABLE[album.size] || PRICE_TABLE.A4 : 0;
  const total = unitPrice * quantity;

  const placeOrder = async (e) => {
    e.preventDefault();
    const required = ["full_name", "street", "city"];
    for (const field of required) {
      if (!address[field]?.trim()) {
        toast.error("Please fill in all required shipping fields");
        return;
      }
    }
    setPlacing(true);
    try {
      const { data } = await api.post("/orders", {
        album_id: albumId,
        quantity,
        shipping_address: address,
      });
      toast.success("Order placed! We're preparing your album.");
      nav(`/orders/${data.id}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to place order");
    } finally {
      setPlacing(false);
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
                <label className="eyebrow block mb-2">Full name</label>
                <input className={inputClass} value={address.full_name} onChange={(e) => setAddress({ ...address, full_name: e.target.value })} required />
              </div>
              <div className="md:col-span-2">
                <label className="eyebrow block mb-2">Phone</label>
                <input className={inputClass} value={address.phone} onChange={(e) => setAddress({ ...address, phone: e.target.value })} />
              </div>
              <div>
                <label className="eyebrow block mb-2">Street</label>
                <input className={inputClass} value={address.street} onChange={(e) => setAddress({ ...address, street: e.target.value })} required />
              </div>
              <div>
                <label className="eyebrow block mb-2">Building</label>
                <input className={inputClass} value={address.building} onChange={(e) => setAddress({ ...address, building: e.target.value })} />
              </div>
              <div className="md:col-span-2">
                <label className="eyebrow block mb-2">City</label>
                <input className={inputClass} value={address.city} onChange={(e) => setAddress({ ...address, city: e.target.value })} required />
              </div>
              <div className="md:col-span-2">
                <label className="eyebrow block mb-2">Additional info (optional)</label>
                <input className={inputClass} value={address.additional_info} onChange={(e) => setAddress({ ...address, additional_info: e.target.value })} placeholder="Floor, gate code, delivery notes..." />
              </div>
            </div>
          </form>

          <aside className="border border-[color:var(--border-soft)] p-6 h-fit">
            <div className="eyebrow mb-5">Order summary</div>
            <div className="text-sm mb-4">
              <div className="flex justify-between mb-1">
                <span className="text-[color:var(--muted)]">Format</span>
                <span>{album.size} · {album.orientation}</span>
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
              disabled={placing}
              className="w-full inline-flex items-center justify-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] py-3 hover:bg-[color:var(--coral)] transition-colors text-sm font-semibold tracking-widest uppercase disabled:opacity-60"
              data-testid="place-order-btn"
            >
              {placing ? <Loader2 size={14} className="animate-spin" /> : null}
              {placing ? "Placing order…" : "Place order"}
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
