import React, { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";
import { useLocalePath } from "@/components/LocalLink";
import { toast } from "sonner";
import { Banknote, CreditCard, Gift, Loader2, Plus, Smartphone, Tag, Trash2 } from "lucide-react";
import { api, coverImageUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useCart } from "@/lib/cart";
import { TERMS_VERSION } from "@/lib/pricing";
import { isLebanesePhone } from "@/lib/phone";
import { getCover, getTemplate } from "@/lib/coverTemplates";
import { payByCard } from "@/lib/cardCheckout";
import { CoverFrontPage } from "@/components/book/CoverFrontPage";
import AreaPicker from "@/components/AreaPicker";
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
  const { t, i18n } = useTranslation();
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
  // The card form being shown: its "Cancel" (aborts payByCard).
  const cardAbort = useRef(null);
  // "cod": cash on delivery (printed albums only); "whish": Whish Pay.
  const [method, setMethod] = useState("cod");

  useEffect(() => {
    refresh();
    api.get("/delivery/areas").then(({ data }) => setAreas(data?.areas || [])).catch(() => {});
    // Once, on opening.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const items = cart?.items || [];
  const hasPrint = items.some((i) => i.kind === "print" && !i.problem);
  const hasProblem = items.some((i) => i.problem);
  // A gift card or a PDF can only be paid online (nothing for a courier to
  // collect the money on); Whish Pay is on once the server has its keys.
  const onlineOnly = Boolean(cart?.needs_online_payment);
  const whishOn = Boolean(cart?.online_payment);
  const cardOn = Boolean(cart?.card_payment);
  // A gift card or a PDF: an online way only (Whish first when both are on).
  const payment = onlineOnly && method === "cod" ? (whishOn ? "whish" : "card") : method;

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
      const { data } = await api.post("/cart/checkout", {
        ...(hasPrint ? { shipping_address: address } : {}),
        accepted_terms_version: TERMS_VERSION,
        payment_method: payment,
        lang: i18n.resolvedLanguage === "fr" ? "fr" : "en",
      });
      // Whish Pay: nothing is ordered yet — the customer pays on Whish's
      // page and comes back to /payment/return (PaymentReturnPage).
      if (data?.payment?.redirect_url) {
        window.location.assign(data.payment.redirect_url);
        return;
      }
      // A card: Cybersource's form, here; its result goes to our server,
      // which checks the payment with Cybersource before ordering.
      if (data?.payment?.session) {
        const paymentId = data.payment.id;
        let result;
        cardAbort.current = new AbortController();
        try {
          result = await payByCard(data.payment.session, { container: "#uc-payment-buttons", signal: cardAbort.current.signal });
        } catch (cardErr) {
          cardAbort.current = null;
          // Closed by the customer, or the form failed to show: its reason
          // goes to the server's logs (never shown as is to the customer).
          let reason = "";
          try {
            // The SDK's errors carry a reason and details besides the message.
            const parts = [cardErr?.reason, cardErr?.message, cardErr?.details && JSON.stringify(cardErr.details)].filter(Boolean);
            reason = parts.length ? parts.join(" | ") : typeof cardErr === "string" ? cardErr : JSON.stringify(cardErr);
          } catch {
            reason = String(cardErr);
          }
          if (!cardErr?.cancelled) console.error("Card form:", cardErr);
          api.post(`/payments/${paymentId}/card`, cardErr?.cancelled ? { cancelled: true } : { cancelled: true, error: String(reason || "unknown").slice(0, 900) }).catch(() => {});
          setPlacing(false);
          toast.error(t("cart.payment.cardNotDone"), { duration: 8000 });
          return;
        }
        cardAbort.current = null;
        await api.post(`/payments/${paymentId}/card`, { result: typeof result === "string" ? result : JSON.stringify(result) }).catch(() => {});
        nav(`/payment/return?payment=${paymentId}&via=card`);
        return;
      }
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
      if (status === 502) {
        toast.error(t(payment === "card" ? "cart.payment.cardDown" : "cart.payment.whishDown"), { duration: 10000 });
        return;
      }
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
          <h1 className="font-serif-display text-4xl md:text-5xl tracking-tight mb-4">{t(payment === "whish" ? "cart.payment.toWhishTitle" : payment === "card" ? "cart.payment.cardTitle" : "checkout.placedTitle")}</h1>
          <p className="text-ink/70">{t(payment === "whish" ? "cart.payment.toWhish" : payment === "card" ? "cart.payment.cardWindow" : "cart.placing")}</p>
          {payment === "card" && (
            <>
              {/* Cybersource's payment buttons (card, wallets) are drawn here;
                  the card form then opens as its side panel. */}
              <div id="uc-payment-buttons" className="mt-8 text-left" data-testid="card-payment-buttons" />
              <button
                type="button"
                onClick={() => cardAbort.current?.abort()}
                className="mt-6 text-sm underline text-ink/70 hover:text-ink"
                data-testid="card-cancel"
              >
                {t("cart.payment.cardCancel")}
              </button>
            </>
          )}
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
                      <AreaPicker
                        areas={areas}
                        className={inputClass}
                        value={address.area}
                        onChange={(area) => setAddress((prev) => ({ ...prev, area }))}
                        placeholder={t("checkout.areaPlaceholder")}
                        testId="checkout-area"
                      />
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

              {/* How it's paid: cash on delivery (printed albums only) or Whish
                  Pay (the only way for a gift card or a PDF); card payment
                  comes later. */}
              {(hasPrint || onlineOnly) && (
                <div className="mt-12" data-testid="cart-payment" role="radiogroup" aria-label={t("cart.payment.title")}>
                  <div className="eyebrow mb-3">{t("cart.payment.title")}</div>
                  <div className="space-y-2">
                    {!onlineOnly && (
                      <PaymentOption
                        selected={payment === "cod"}
                        onSelect={() => setMethod("cod")}
                        Icon={Banknote}
                        label={t("cart.payment.cod")}
                        hint={t("cart.payment.codHint")}
                        tid="cart-payment-cod"
                      />
                    )}
                    <PaymentOption
                      selected={payment === "whish"}
                      onSelect={() => setMethod("whish")}
                      disabled={!whishOn}
                      Icon={Smartphone}
                      label={t("cart.payment.whish")}
                      hint={whishOn ? t("cart.payment.whishHint") : null}
                      soon={!whishOn && t("cart.payment.soon")}
                      tid="cart-payment-whish"
                    />
                    <PaymentOption
                      selected={payment === "card"}
                      onSelect={() => setMethod("card")}
                      disabled={!cardOn}
                      Icon={CreditCard}
                      label={t("cart.payment.card")}
                      hint={cardOn ? t("cart.payment.cardHint") : null}
                      soon={!cardOn && t("cart.payment.soon")}
                      tid="cart-payment-card"
                    />
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
                {cart.discount_cents > 0 && (
                  <div className="flex justify-between text-[color:var(--coral)] pt-1" data-testid="cart-discount">
                    <span>{t("cart.promo.line", { code: cart.promo.code, percent: cart.promo.percent })}</span>
                    <span>−{money(cart.discount_cents)}</span>
                  </div>
                )}
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
              {hasPrint && payment === "cod" && cart.cash_cents !== cart.total_cents && (
                <div className="flex justify-between text-sm -mt-3 mb-6" data-testid="cart-cash">
                  <span className="text-[color:var(--muted)]">{t("checkout.cashToCourier")}</span>
                  <span>{money(cart.cash_cents)}</span>
                </div>
              )}
              {cart.credit_applied_cents > 0 && cart.total_cents === 0 && (
                <p className="text-xs text-[color:var(--coral)] -mt-3 mb-6" data-testid="cart-covered">{t(cart.discount_cents > 0 ? "cart.nothingToPay" : "cart.coveredByGift")}</p>
              )}
              {cart.credit_balance_cents > cart.credit_applied_cents && cart.credit_applied_cents > 0 && (
                <p className="text-xs text-[color:var(--muted)] -mt-3 mb-6">{t("cart.creditLeft", { amount: money(cart.credit_balance_cents - cart.credit_applied_cents) })}</p>
              )}
              <PromoBox cart={cart} />
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
                disabled={hasProblem || placing || (onlineOnly && !whishOn && !cardOn)}
                className="w-full inline-flex items-center justify-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] py-3 hover:bg-[color:var(--coral)] transition-colors text-sm font-semibold tracking-widest uppercase disabled:opacity-50"
                data-testid="place-order-btn"
              >
                {placing ? <Loader2 size={16} className="animate-spin" /> : payment === "whish" && cart.total_cents > 0 ? t("cart.payment.payWithWhish") : payment === "card" && cart.total_cents > 0 ? t("cart.payment.payByCard") : t("checkout.placeOrder")}
              </button>
              <div className="text-[11px] text-[color:var(--muted)] mt-3 leading-relaxed space-y-2">
                {hasPrint && payment === "cod" && cart.cash_cents > 0 && <p>{t("checkout.noPayment")}</p>}
                {payment === "whish" && whishOn && cart.total_cents > 0 && <p data-testid="cart-whish-note">{t("cart.payment.whishNote")}</p>}
                {payment === "card" && cardOn && cart.total_cents > 0 && <p data-testid="cart-card-note">{t("cart.payment.cardNote")}</p>}
              </div>
            </aside>
          </div>
        )}
      </div>
    </main>
  );
}

// One way to pay, as a radio button (a coming-soon one shown, greyed).
function PaymentOption({ selected = false, onSelect, disabled = false, Icon, label, hint, soon, tid }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      aria-disabled={disabled}
      disabled={disabled}
      onClick={onSelect}
      className={`w-full text-left px-4 py-3 flex items-start gap-3 border transition-colors ${
        selected ? "border-[color:var(--ink)] bg-white" : "border-ink/15 hover:border-ink/40"
      } ${disabled ? "opacity-60 cursor-not-allowed hover:border-ink/15" : ""}`}
      data-testid={tid}
    >
      <span
        className={`mt-1 w-3.5 h-3.5 rounded-full shrink-0 ${selected ? "border-[4px] border-[color:var(--ink)]" : "border border-ink/40"}`}
        aria-hidden="true"
      />
      <span className="flex-1 text-sm">
        <span className="font-medium flex items-center gap-2"><Icon size={16} className={selected ? "text-[color:var(--coral)]" : ""} /> {label}</span>
        {hint && <span className="block text-xs text-[color:var(--muted)] mt-0.5">{hint}</span>}
      </span>
      {soon && <span className="text-[10px] font-semibold tracking-widest uppercase text-[color:var(--muted)] self-center">{soon}</span>}
    </button>
  );
}

// The promo code: typed and applied, or shown with a way to remove it (and,
// when it stopped working meanwhile, why).
function PromoBox({ cart }) {
  const { t } = useTranslation();
  const { applyPromo, removePromo } = useCart();
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const promo = cart.promo;

  const apply = async () => {
    if (!code.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      await applyPromo(code.trim());
      setCode("");
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(t(`cart.promo.errors.${typeof detail === "string" ? detail.replace("promo_", "") : "unknown"}`, { defaultValue: t("cart.promo.errors.unknown") }));
    } finally {
      setBusy(false);
    }
  };

  if (promo) {
    return (
      <div className="mb-5 text-xs" data-testid="cart-promo-applied">
        <div className="flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 font-semibold tracking-wider"><Tag size={12} className="text-[color:var(--coral)]" /> {promo.code}</span>
          <button type="button" onClick={() => removePromo()} className="text-[color:var(--muted)] underline hover:text-red-700" data-testid="cart-promo-remove">
            {t("cart.remove")}
          </button>
        </div>
        {promo.problem && <p className="text-red-700 mt-1" data-testid="cart-promo-problem">{t(`cart.promo.errors.${promo.problem}`)}</p>}
        {!promo.problem && cart.credit_balance_cents > 0 && (
          <p className="text-[color:var(--muted)] mt-1.5 leading-relaxed" data-testid="cart-promo-no-credit">
            {t("cart.promo.noCredit", { amount: money(cart.credit_balance_cents) })}
          </p>
        )}
      </div>
    );
  }
  return (
    <div className="mb-5">
      <label className="eyebrow block mb-2" htmlFor="promo-code">{t("cart.promo.label")}</label>
      <div className="flex gap-2">
        <input
          id="promo-code"
          className="flex-1 min-w-0 border border-ink/20 px-3 py-2 text-sm uppercase bg-white focus:border-[color:var(--ink)] focus:outline-none"
          value={code}
          onChange={(e) => {
            setCode(e.target.value);
            setError("");
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              apply();
            }
          }}
          data-testid="cart-promo-input"
        />
        <button
          type="button"
          onClick={apply}
          disabled={!code.trim() || busy}
          className="shrink-0 border border-[color:var(--ink)] px-3 text-xs font-semibold tracking-widest uppercase hover:bg-[color:var(--ink)] hover:text-[color:var(--paper)] transition-colors disabled:opacity-40"
          data-testid="cart-promo-apply"
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : t("cart.promo.apply")}
        </button>
      </div>
      {error && <p className="text-xs text-red-700 mt-1.5" data-testid="cart-promo-error">{error}</p>}
    </div>
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
        {item.problem && (
          <p className="text-xs text-red-700 mt-2" data-testid="cart-item-problem">{t(`cart.problem.${item.problem}`)}</p>
        )}
        <div className="flex items-center gap-4 mt-3">
          <button type="button" onClick={onRemove} className="inline-flex items-center gap-1 text-xs text-[color:var(--muted)] hover:text-red-700" data-testid="cart-remove-gift">
            <Trash2 size={12} /> {t("cart.remove")}
          </button>
        </div>
      </div>
    </li>
  );
}
