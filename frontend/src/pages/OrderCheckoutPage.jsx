import React, { useEffect, useState } from "react";
import { useParams, useNavigate, useSearchParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { useCart } from "@/lib/cart";
import { toast } from "sonner";
import { ArrowLeft, Check, Loader2 } from "lucide-react";
import { FREE_TRIAL, SHIPPING_PRICE, billedPageCount, computeDigitalPrice, computeUnitPrice } from "@/lib/pricing";
import { darkPhotoItems, lowResolutionItems } from "@/lib/printQuality";

/**
 * Choosing what to order for one album — the printed book, the PDF, or
 * both — then adding it to the cart (lib/cart.jsx). The delivery address,
 * the terms and the order itself are on the cart page, once for all the
 * albums in it (CartPage).
 */
export default function OrderCheckoutPage() {
  const { albumId } = useParams();
  const nav = useNavigate();
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const { cart, refresh, add, remove } = useCart();
  const [album, setAlbum] = useState(null);
  // What's chosen: { print: bool, digital: bool }. One order of each per
  // album: a version already ordered can't be chosen again.
  const [kinds, setKinds] = useState({ print: searchParams.get("kind") !== "digital", digital: searchParams.get("kind") === "digital" });
  const [orderedKinds, setOrderedKinds] = useState({});
  const [quantity, setQuantity] = useState(1);
  const [busy, setBusy] = useState(false);
  // Gift card credit on the account: taken off what's added here.
  const [credit, setCredit] = useState(0);
  useEffect(() => {
    api.get("/credits").then(({ data }) => setCredit((data?.balance_cents || 0) / 100)).catch(() => {});
  }, []);
  const inCart = (cart?.items || []).filter((i) => i.album_id === albumId);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/albums/${albumId}`);
        setAlbum(data);
        if (data.was_ordered) {
          try {
            const { data: orders } = await api.get("/orders");
            const mine = (orders || []).filter((o) => o.album_id === albumId && o.status !== "cancelled");
            const byKind = Object.fromEntries(mine.map((o) => [o.kind || "print", o]));
            if (byKind.print && byKind.digital) {
              nav(`/orders/${mine[0].id}`, { replace: true });
              return;
            }
            setOrderedKinds(byKind);
            setKinds({ print: !byKind.print, digital: !!byKind.print });
          } catch {
            /* the server refuses a version already ordered anyway */
          }
        }
      } catch {
        toast.error(t("checkout.loadError"));
      }
      // Already in the cart: shown as it is there.
      const current = await refresh();
      const mineInCart = (current?.items || []).filter((i) => i.album_id === albumId);
      if (mineInCart.length) {
        setKinds({ print: mineInCart.some((i) => i.kind === "print"), digital: mineInCart.some((i) => i.kind === "digital") });
        const printed = mineInCart.find((i) => i.kind === "print");
        if (printed) setQuantity(printed.quantity);
      }
    })();
    // Loaded once per album.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [albumId]);

  const lowResCount = album ? lowResolutionItems(album).length : 0;
  const darkCount = album ? darkPhotoItems(album).length : 0;
  const pageCount = album ? billedPageCount(album) : 0;
  const printPrice = album ? computeUnitPrice(album.size || "A4", pageCount) : 0;
  const digitalPrice = album ? computeDigitalPrice(album.size || "A4", pageCount) : 0;
  const subtotal = (kinds.print ? printPrice * quantity : 0) + (kinds.digital ? digitalPrice : 0);
  // With a gift card, the delivery is counted here too (the card includes
  // it), then the card's credit taken off.
  const withDelivery = subtotal + (credit > 0 && kinds.print && !orderedKinds.print ? SHIPPING_PRICE : 0);
  const giftCovers = Math.min(credit, withDelivery);
  const nothingChosen = !kinds.print && !kinds.digital;

  const addToCart = async () => {
    if (nothingChosen || busy) return;
    setBusy(true);
    try {
      for (const kind of ["print", "digital"]) {
        const line = inCart.find((i) => i.kind === kind);
        if (kinds[kind]) await add(albumId, kind, kind === "print" ? quantity : 1);
        else if (line) await remove(line.id);
      }
      nav("/cart");
    } catch (err) {
      const status = err?.response?.status;
      toast.error(status === 409 ? t("checkout.alreadyOrdered") : err?.response?.data?.detail || t("checkout.checkAlbum"));
      setBusy(false);
    }
  };

  if (!album) {
    return (
      <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
        <div className="max-w-[900px] mx-auto text-sm text-[color:var(--muted)]">{t("checkout.loading")}</div>
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
          <div>
            <div className="eyebrow mb-1">{t("checkout.kindTitle")}</div>
            <p className="text-xs text-[color:var(--muted)] mb-4">{t("cart.chooseBoth")}</p>
            <div className="grid sm:grid-cols-2 gap-3 mb-6" data-testid="checkout-kind">
              {[
                { value: "print", price: printPrice, extra: t("checkout.kindPrintExtra", { price: SHIPPING_PRICE.toFixed(2) }) },
                { value: "digital", price: digitalPrice, extra: t("checkout.kindDigitalExtra") },
              ].map((option) => {
                const taken = Boolean(orderedKinds[option.value]);
                const chosen = kinds[option.value] && !taken;
                return (
                  <button
                    key={option.value}
                    type="button"
                    role="checkbox"
                    aria-checked={chosen}
                    disabled={taken}
                    onClick={() => setKinds((k) => ({ ...k, [option.value]: !k[option.value] }))}
                    data-testid={`checkout-kind-${option.value}`}
                    className={`text-left border p-4 transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                      chosen ? "border-[color:var(--ink)] bg-white" : "border-[color:var(--ink)]/20 hover:border-[color:var(--ink)]/50"
                    }`}
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="inline-flex items-center gap-2 font-semibold">
                        <span className={`inline-flex items-center justify-center w-4 h-4 border ${chosen ? "bg-[color:var(--ink)] border-[color:var(--ink)] text-[color:var(--paper)]" : "border-[color:var(--ink)]/40"}`}>
                          {chosen && <Check size={12} strokeWidth={3} />}
                        </span>
                        {t(`checkout.kind.${option.value}`)}
                      </span>
                      <OfferedPrice price={option.price} />
                    </div>
                    <p className="text-xs text-[color:var(--muted)] mt-1">{taken ? t("checkout.kindAlreadyOrdered") : option.extra}</p>
                  </button>
                );
              })}
            </div>
            {kinds.digital && (
              <p className="text-sm text-[color:var(--ink)]/80 leading-relaxed mb-4" data-testid="checkout-digital-note">
                {t("checkout.digitalNote")}
              </p>
            )}
            {kinds.print && !orderedKinds.print && (
              <p className="text-xs text-[color:var(--muted)]" data-testid="checkout-delivery-time">{t("checkout.deliveryTime")}</p>
            )}
          </div>

          <aside className="border border-[color:var(--border-soft)] p-6 h-fit">
            <div className="eyebrow mb-5">{t("checkout.summary")}</div>
            <div className="text-sm mb-4">
              <div className="flex justify-between mb-1">
                <span className="text-[color:var(--muted)]">{t("checkout.format")}</span>
                <span>{album.size} · {album.orientation === "landscape" ? t("createAlbum.format.landscapeLower") : t("createAlbum.format.portraitLower")}</span>
              </div>
              <div className="flex justify-between mb-1">
                <span className="text-[color:var(--muted)]">{t("checkout.pages")}</span>
                <span>{pageCount}</span>
              </div>
              {kinds.print && (
                <>
                  <div className="text-xs text-[color:var(--muted)] bg-[color:var(--editor-canvas)] border border-[color:var(--border-soft)] rounded px-2 py-1.5 mb-3 mt-1">
                    {t("checkout.previewQuality")}
                  </div>
                  {lowResCount > 0 && (
                    <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1.5 mb-3" data-testid="checkout-low-res">
                      {t("checkout.lowResolution", { count: lowResCount })}{" "}
                      <Link to={`/editor/${albumId}`} className="underline">{t("checkout.backToEditing")}</Link>
                    </div>
                  )}
                  {darkCount > 0 && (
                    <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1.5 mb-3" data-testid="checkout-dark">
                      {t("checkout.tooDark", { count: darkCount })}{" "}
                      <Link to={`/editor/${albumId}`} className="underline">{t("checkout.backToEditing")}</Link>
                    </div>
                  )}
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-[color:var(--muted)]">{t("checkout.quantity")}</span>
                    <input
                      type="number"
                      min={1}
                      max={20}
                      value={quantity}
                      onChange={(e) => setQuantity(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
                      className="w-16 border border-[color:var(--ink)]/20 p-1 text-sm text-center focus:border-[color:var(--ink)] focus:outline-none"
                      data-testid="checkout-quantity"
                    />
                  </div>
                  <div className="flex justify-between mb-1">
                    <span className="text-[color:var(--muted)]">{t("checkout.kind.print")}</span>
                    <OfferedPrice price={printPrice * quantity} />
                  </div>
                </>
              )}
              {kinds.digital && (
                <div className="flex justify-between mb-1">
                  <span className="text-[color:var(--muted)]">{t("checkout.kind.digital")}</span>
                  <OfferedPrice price={digitalPrice} />
                </div>
              )}
              {kinds.print && credit > 0 && (
                <div className="flex justify-between mb-1">
                  <span className="text-[color:var(--muted)]">{t("checkout.shipping")}</span>
                  <span>${SHIPPING_PRICE.toFixed(2)}</span>
                </div>
              )}
              {giftCovers > 0 && (
                <div className="flex justify-between mb-1 text-[color:var(--coral)]" data-testid="checkout-gift-credit">
                  <span>{t("cart.credit")}</span>
                  <span>−${giftCovers.toFixed(2)}</span>
                </div>
              )}
              {kinds.print && credit <= 0 && <p className="text-xs text-[color:var(--muted)] mt-2">{t("cart.deliveryOnce", { price: SHIPPING_PRICE.toFixed(2) })}</p>}
            </div>
            <div className="flex justify-between text-base font-medium border-t border-[color:var(--border-soft)] pt-4 mb-2" data-testid="checkout-subtotal">
              <span>{t(credit > 0 ? "checkout.total" : "cart.subtotal")}</span>
              <span>${(withDelivery - giftCovers).toFixed(2)}</span>
            </div>
            {giftCovers > 0 && (
              <p className="text-xs text-[color:var(--coral)] mb-6">
                {withDelivery - giftCovers <= 0 ? t("cart.coveredByGift") : t("cart.partlyCoveredByGift", { amount: (withDelivery - giftCovers).toFixed(2) })}
              </p>
            )}
            {!giftCovers && <div className="mb-4" />}
            <button
              type="button"
              onClick={addToCart}
              disabled={nothingChosen || busy}
              className="w-full inline-flex items-center justify-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] py-3 hover:bg-[color:var(--coral)] transition-colors text-sm font-semibold tracking-widest uppercase disabled:opacity-50"
              data-testid="add-to-cart-btn"
            >
              {busy && <Loader2 size={14} className="animate-spin" />}
              {t(inCart.length ? "cart.update" : "cart.add")}
            </button>
            <p className="text-[11px] text-[color:var(--muted)] mt-3 leading-relaxed">{t("cart.addHint")}</p>
          </aside>
        </div>
      </div>
    </main>
  );
}

// An album's price; during the test week, struck through and "Free".
export function OfferedPrice({ price }) {
  const { t } = useTranslation();
  if (!FREE_TRIAL) return <span>${price.toFixed(2)}</span>;
  return (
    <span className="whitespace-nowrap" data-testid="offered-price">
      <span className="line-through text-[color:var(--muted)] mr-1.5">${price.toFixed(2)}</span>
      <span className="font-semibold text-[color:var(--coral)]">{t("checkout.free")}</span>
    </span>
  );
}
