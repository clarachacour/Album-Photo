import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";
import { useLocalePath } from "@/components/LocalLink";
import { toast } from "sonner";
import { CreditCard, Gift, Loader2, Plus, Trash2 } from "lucide-react";
import { api, coverImageUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useCart } from "@/lib/cart";
import { TERMS_VERSION } from "@/lib/pricing";
import { isLebanesePhone } from "@/lib/phone";
import { getCover, getTemplate } from "@/lib/coverTemplates";
import { CoverFrontPage } from "@/components/book/CoverFrontPage";
import { usePageMeta } from "@/hooks/usePageMeta";

const money = (cents) => `$${(cents / 100).toFixed(2)}`;

/**
 * The cart: every album the customer added (printed, PDF, or both), one
 * delivery address for the printed ones, the terms, one total — and one
 * click to order everything (POST /cart/checkout). The printed albums are
 * delivered together, the delivery paid once.
 */
export default function CartPage() {
  usePageMeta("cart");
  const { t } = useTranslation();
  const lp = useLocalePath();
  const nav = useNavigate();
  const { user } = useAuth();
  const { cart, refresh, setQuantity, remove, setCart } = useCart();
  const [address, setAddress] = useState({
    full_name: user?.name || "",
    phone: user?.phone || "",
    street: user?.street || "",
    building: user?.building || "",
    city: user?.city || "",
    area: "",
    additional_info: user?.additional_info || "",
    country: "Lebanon", // delivery in Lebanon only
  });
  // The courier's (Wakilni's) area names, suggested for the "Area" field;
  // when there's a list, the area must be one of them.
  const [areas, setAreas] = useState([]);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [termsError, setTermsError] = useState(false);
  const [phoneError, setPhoneError] = useState(false);
  const [placing, setPlacing] = useState(false);

  useEffect(() => {
    refresh();
    api.get("/delivery/areas").then(({ data }) => setAreas(data?.areas || [])).catch(() => {});
    // Once, on opening.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const items = cart?.items || [];
  const hasPrint = items.some((i) => i.kind === "print" && !i.problem);
  const hasDigital = items.some((i) => i.kind === "digital" && !i.problem);
  const hasGift = items.some((i) => i.kind === "gift");
  const hasProblem = items.some((i) => i.problem);

  const placeOrder = async (e) => {
    e.preventDefault();
    if (hasProblem) {
      toast.error(t("cart.fixProblems"));
      return;
    }
    if (hasPrint) {
      for (const field of ["full_name", "phone", "street", "city", ...(areas.length ? ["area"] : [])]) {
        if (!address[field]?.trim()) {
          toast.error(t("checkout.requiredFields"));
          return;
        }
      }
      if (!isLebanesePhone(address.phone)) {
        setPhoneError(true);
        toast.error(t("checkout.phoneInvalid"));
        return;
      }
      if (areas.length && !areas.some((a) => a.toLowerCase() === address.area.trim().toLowerCase())) {
        toast.error(t("checkout.areaFromList"));
        return;
      }
    }
    if (!acceptedTerms) {
      setTermsError(true);
      toast.error(t("checkout.mustAcceptTerms"));
      return;
    }
    setPlacing(true);
    try {
      await api.post("/cart/checkout", {
        ...(hasPrint ? { shipping_address: address } : {}),
        accepted_terms_version: TERMS_VERSION,
      });
      setCart({ ...cart, items: [], count: 0 });
      refresh();
      nav("/orders");
    } catch (err) {
      // The orders are created first, before the PDFs are started: past the
      // known refusals below, they're almost always placed already (a slow
      // or dropped connection) — the customer is sent to their orders.
      setPlacing(false);
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail || "";
      if (status === 409) {
        toast.error(t("cart.fixProblems"));
        refresh();
        return;
      }
      if (status === 400 && /terms of sale/i.test(detail)) {
        toast.error(t("checkout.termsChanged"), { duration: 10000 });
        return;
      }
      if (status === 400 || status === 404) {
        toast.error(detail || t("checkout.checkAlbum"));
        refresh();
        return;
      }
      toast.info(t("checkout.slow"));
      refresh();
      nav("/orders", { replace: true });
    }
  };

  const inputClass =
    "w-full border border-ink/20 p-3 text-sm bg-white focus:border-[color:var(--ink)] focus:outline-none";

  if (placing) {
    return (
      <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12 flex items-center justify-center">
        <div className="max-w-[500px] mx-auto text-center animate-fade-up">
          <Loader2 className="w-6 h-6 animate-spin mx-auto mb-6 text-[color:var(--muted)]" />
          <h1 className="font-serif-display text-4xl md:text-5xl tracking-tight mb-4">{t("checkout.placedTitle")}</h1>
          <p className="text-ink/70">{t("cart.placing")}</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
      <div className="max-w-[1000px] mx-auto">
        <div className="mb-10">
          <div className="eyebrow mb-3">{t("cart.eyebrow")}</div>
          <h1 className="font-serif-display text-4xl md:text-5xl tracking-tight">{t("cart.title")}</h1>
        </div>

        {!cart ? (
          <p className="text-sm text-[color:var(--muted)]">{t("checkout.loading")}</p>
        ) : items.length === 0 ? (
          <div className="border border-dashed border-ink/20 py-20 px-8 text-center" data-testid="cart-empty">
            <p className="font-serif-display text-3xl mb-4">{t("cart.empty")}</p>
            <Link to="/dashboard" className="inline-block bg-[color:var(--ink)] text-[color:var(--paper)] px-8 py-4 text-sm font-semibold tracking-widest uppercase hover:bg-[color:var(--coral)] transition-colors">
              {t("cart.toAlbums")}
            </Link>
          </div>
        ) : (
          <div className="grid md:grid-cols-[1fr_320px] gap-12">
            <form onSubmit={placeOrder} id="cart-form" noValidate>
              <ul className="divide-y divide-[color:var(--border-soft)] border-y border-[color:var(--border-soft)] mb-4" data-testid="cart-items">
                {items.map((item) =>
                  item.kind === "gift" ? (
                    <GiftLine key={item.id} item={item} onRemove={() => remove(item.id)} />
                  ) : (
                    <CartLine key={item.id} item={item} onQuantity={(q) => setQuantity(item.id, q)} onRemove={() => remove(item.id)} />
                  )
                )}
              </ul>
              <Link to="/dashboard" className="inline-flex items-center gap-2 text-sm text-ink/80 hover:text-[color:var(--coral)] mb-12" data-testid="cart-add-another">
                <Plus size={14} /> {t("cart.addAnother")}
              </Link>

              {hasPrint && (
                <>
                  <div className="eyebrow mb-2">{t("checkout.shippingAddress")}</div>
                  <p className="text-xs text-[color:var(--muted)] mb-6">{t("cart.oneAddress")}</p>
                  <div className="grid md:grid-cols-2 gap-4 mb-4">
                    <div className="md:col-span-2">
                      <label className="eyebrow block mb-2">{t("checkout.fullName")}</label>
                      <input className={inputClass} value={address.full_name} onChange={(e) => setAddress({ ...address, full_name: e.target.value })} required />
                    </div>
                    <div className="md:col-span-2">
                      <label className="eyebrow block mb-2">{t("checkout.phone")}</label>
                      <input
                        className={`${inputClass} ${phoneError ? "border-red-500" : ""}`}
                        value={address.phone}
                        onChange={(e) => {
                          setAddress({ ...address, phone: e.target.value });
                          setPhoneError(false);
                        }}
                        onBlur={() => address.phone && setPhoneError(!isLebanesePhone(address.phone))}
                        type="tel"
                        inputMode="tel"
                        placeholder="70 123 456"
                        data-testid="checkout-phone"
                        required
                      />
                      {phoneError && <p className="text-xs text-red-600 mt-1" data-testid="checkout-phone-error">{t("checkout.phoneInvalid")}</p>}
                    </div>
                    <div>
                      <label className="eyebrow block mb-2">{t("checkout.street")}</label>
                      <input className={inputClass} value={address.street} onChange={(e) => setAddress({ ...address, street: e.target.value })} required />
                    </div>
                    <div>
                      <label className="eyebrow block mb-2">{t("checkout.building")}</label>
                      <input className={inputClass} value={address.building} onChange={(e) => setAddress({ ...address, building: e.target.value })} />
                    </div>
                    <div>
                      <label className="eyebrow block mb-2">{t("checkout.city")}</label>
                      <input className={inputClass} value={address.city} onChange={(e) => setAddress({ ...address, city: e.target.value })} required />
                    </div>
                    <div>
                      <label className="eyebrow block mb-2">{t(areas.length ? "checkout.areaRequired" : "checkout.area")}</label>
                      <input
                        className={inputClass}
                        list="delivery-areas"
                        value={address.area}
                        onChange={(e) => setAddress({ ...address, area: e.target.value })}
                        placeholder={t("checkout.areaPlaceholder")}
                        data-testid="checkout-area"
                      />
                      <datalist id="delivery-areas">
                        {areas.map((a) => <option key={a} value={a} />)}
                      </datalist>
                    </div>
                    <div>
                      <label className="eyebrow block mb-2">{t("checkout.country")}</label>
                      {/* Delivery in Lebanon only: filled in, not editable. */}
                      <input className={`${inputClass} opacity-70 cursor-not-allowed`} value={t("checkout.lebanon")} disabled readOnly data-testid="checkout-country" />
                    </div>
                    <div className="md:col-span-2">
                      <label className="eyebrow block mb-2">{t("checkout.additionalInfo")}</label>
                      <input className={inputClass} value={address.additional_info} onChange={(e) => setAddress({ ...address, additional_info: e.target.value })} placeholder={t("checkout.additionalInfoPlaceholder")} />
                    </div>
                  </div>
                  <p className="text-xs text-[color:var(--muted)] mt-1">{t("checkout.required")}</p>
                </>
              )}

              {/* The payment step: gift cards are paid here. Online payment
                  isn't set up yet — the card is activated without charging
                  (backend services/payments.py, to update then). */}
              {hasGift && (
                <div className={`${hasPrint ? "mt-12" : ""}`} data-testid="cart-payment">
                  <div className="eyebrow mb-2">{t("cart.payment.title")}</div>
                  <div className="border border-dashed border-ink/25 bg-white px-5 py-4 flex items-start gap-3">
                    <CreditCard size={18} className="mt-0.5 text-[color:var(--muted)] shrink-0" />
                    <div className="text-sm">
                      <p className="font-medium">{t("cart.payment.amount", { amount: money(cart.pay_now_cents) })}</p>
                      <p className="text-[color:var(--muted)] text-xs mt-1">{t("cart.payment.notYet")}</p>
                    </div>
                  </div>
                </div>
              )}
            </form>

            <aside className="border border-[color:var(--border-soft)] p-6 h-fit md:sticky md:top-24">
              <div className="eyebrow mb-5">{t("checkout.summary")}</div>
              <div className="text-sm space-y-1 mb-4">
                <div className="flex justify-between">
                  <span className="text-[color:var(--muted)]">{t("cart.items", { count: items.filter((i) => !i.problem).length })}</span>
                  <span>{money(cart.subtotal_cents)}</span>
                </div>
                {hasPrint && (
                  <div className="flex justify-between">
                    <span className="text-[color:var(--muted)]">{t("checkout.shipping")}</span>
                    <span>{money(cart.shipping_cents)}</span>
                  </div>
                )}
                {hasPrint && <p className="text-xs text-[color:var(--muted)] pt-1">{t("cart.deliveredTogether")}</p>}
                {/* Gift card credit on the account, taken off the albums. */}
                {cart.credit_applied_cents > 0 && (
                  <div className="flex justify-between text-[color:var(--coral)] pt-1" data-testid="cart-credit">
                    <span>{t("cart.credit")}</span>
                    <span>−{money(cart.credit_applied_cents)}</span>
                  </div>
                )}
              </div>
              <div className="flex justify-between text-base font-medium border-t border-[color:var(--border-soft)] pt-4 mb-6" data-testid="cart-total">
                <span>{t("checkout.total")}</span>
                <span>{money(cart.total_cents)}</span>
              </div>
              {/* What the courier collects: the printed albums and the
                  delivery (a PDF has nothing to pay while online payment
                  isn't set up). */}
              {hasPrint && cart.cash_cents !== cart.total_cents && (
                <div className="flex justify-between text-sm -mt-3 mb-6" data-testid="cart-cash">
                  <span className="text-[color:var(--muted)]">{t("checkout.cashToCourier")}</span>
                  <span>{money(cart.cash_cents)}</span>
                </div>
              )}
              {cart.credit_applied_cents > 0 && cart.total_cents === 0 && (
                <p className="text-xs text-[color:var(--coral)] -mt-3 mb-6" data-testid="cart-covered">{t("cart.coveredByGift")}</p>
              )}
              {cart.credit_balance_cents > cart.credit_applied_cents && cart.credit_applied_cents > 0 && (
                <p className="text-xs text-[color:var(--muted)] -mt-3 mb-6">{t("cart.creditLeft", { amount: money(cart.credit_balance_cents - cart.credit_applied_cents) })}</p>
              )}
              <label className={`flex items-start gap-2 text-xs leading-relaxed mb-4 cursor-pointer ${termsError ? "text-red-700" : "text-ink/80"}`}>
                <input
                  type="checkbox"
                  checked={acceptedTerms}
                  onChange={(e) => {
                    setAcceptedTerms(e.target.checked);
                    if (e.target.checked) setTermsError(false);
                  }}
                  className="mt-0.5 accent-[color:var(--ink)]"
                  aria-invalid={termsError}
                  data-testid="accept-terms"
                />
                <span>
                  <Trans
                    i18nKey="checkout.acceptTerms"
                    components={{ terms: <Link to={lp("/terms")} target="_blank" rel="noopener" className="underline hover:text-[color:var(--coral)]" /> }}
                  />
                </span>
              </label>
              <button
                type="submit"
                form="cart-form"
                disabled={hasProblem}
                className="w-full inline-flex items-center justify-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] py-3 hover:bg-[color:var(--coral)] transition-colors text-sm font-semibold tracking-widest uppercase disabled:opacity-50"
                data-testid="place-order-btn"
              >
                {t("checkout.placeOrder")}
              </button>
              <div className="text-[11px] text-[color:var(--muted)] mt-3 leading-relaxed space-y-2">
                {hasPrint && cart.cash_cents > 0 && <p>{t("checkout.noPayment")}</p>}
                {hasDigital && <p>{t("checkout.noPaymentDigital")}</p>}
              </div>
            </aside>
          </div>
        )}
      </div>
    </main>
  );
}

function CartLine({ item, onQuantity, onRemove }) {
  const { t } = useTranslation();
  const album = item.album || {};
  const digital = item.kind === "digital";
  return (
    <li className="py-5 flex gap-4 items-start" data-testid={`cart-item-${item.kind}-${item.album_id}`}>
      <Link to={`/order/${item.album_id}`} className="block w-16 shrink-0" aria-hidden="true" tabIndex={-1}>
        <CoverFrontPage
          template={getTemplate()}
          cover={getCover(album.cover)}
          templateId={album.cover_template_id}
          title={album.title || t("dashboard.untitled")}
          orientation={album.orientation || "portrait"}
          coverImageUrl={album.cover_image_path ? coverImageUrl(album.id) : undefined}
          editable={false}
        />
      </Link>
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="font-medium truncate">{album.title || t("dashboard.untitled")}</p>
            <p className="text-xs text-[color:var(--muted)]">
              {t(`checkout.kind.${digital ? "digital" : "print"}`)} · {album.size} · {t("cart.pages", { count: item.page_count })}
            </p>
          </div>
          <span className="text-sm whitespace-nowrap">{money(item.line_total_cents)}</span>
        </div>
        {item.problem && (
          <p className="text-xs text-red-700 mt-2" data-testid="cart-item-problem">{t(`cart.problem.${item.problem}`)}</p>
        )}
        <div className="flex items-center gap-4 mt-3">
          {!digital && (
            <label className="flex items-center gap-2 text-xs text-[color:var(--muted)]">
              {t("checkout.quantity")}
              <input
                type="number"
                min={1}
                max={20}
                defaultValue={item.quantity}
                onBlur={(e) => {
                  const q = Math.max(1, Math.min(20, Number(e.target.value) || 1));
                  e.target.value = q;
                  if (q !== item.quantity) onQuantity(q);
                }}
                className="w-14 border border-ink/20 p-1 text-sm text-center text-[color:var(--ink)] focus:border-[color:var(--ink)] focus:outline-none"
                data-testid={`cart-quantity-${item.album_id}`}
              />
            </label>
          )}
          <Link to={`/order/${item.album_id}`} className="text-xs underline text-ink/70 hover:text-[color:var(--ink)]">
            {t("cart.change")}
          </Link>
          <button type="button" onClick={onRemove} className="inline-flex items-center gap-1 text-xs text-[color:var(--muted)] hover:text-red-700" data-testid={`cart-remove-${item.kind}-${item.album_id}`}>
            <Trash2 size={12} /> {t("cart.remove")}
          </button>
        </div>
      </div>
    </li>
  );
}

function GiftLine({ item, onRemove }) {
  const { t } = useTranslation();
  return (
    <li className="py-5 flex gap-4 items-start" data-testid="cart-item-gift">
      <div className="w-16 shrink-0 aspect-[148/105] bg-[#F7F3EB] border border-[color:var(--border-soft)] flex items-center justify-center border-l-4 border-l-[color:var(--coral)]">
        <Gift size={18} className="text-[color:var(--coral)]" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="font-medium truncate">{t("cart.gift.title", { name: item.recipient_name || "…" })}</p>
            <p className="text-xs text-[color:var(--muted)]">{t("cart.gift.detail", { size: item.size, pages: item.page_tier })}</p>
          </div>
          <span className="text-sm whitespace-nowrap">{money(item.line_total_cents)}</span>
        </div>
        <div className="flex items-center gap-4 mt-3">
          <button type="button" onClick={onRemove} className="inline-flex items-center gap-1 text-xs text-[color:var(--muted)] hover:text-red-700" data-testid="cart-remove-gift">
            <Trash2 size={12} /> {t("cart.remove")}
          </button>
        </div>
      </div>
    </li>
  );
}
