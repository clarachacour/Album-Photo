import React, { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useCart } from "@/lib/cart";
import { rememberAfterLogin } from "@/lib/afterLogin";
import { ONLINE_PAYMENT, PAGE_TIERS, SHIPPING_PRICE, computeUnitPrice } from "@/lib/pricing";
import { usePageMeta } from "@/hooks/usePageMeta";

// The form, kept for the tab while the visitor signs in to add it to the cart.
const DRAFT_KEY = "everbook_gift_draft";

/** What a gift card is worth (and costs): the album, delivery included. */
export const giftValue = (size, pages) => computeUnitPrice(size, pages) + SHIPPING_PRICE;

/**
 * Gift cards: offering an album (a format, a page count, a few words — the
 * card is a PDF, see backend services/gift_cards.py), and, below, using the
 * code from a card received.
 */
export default function GiftPage() {
  usePageMeta("gift");
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const { addGift } = useCart();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const lang = i18n.language?.startsWith("fr") ? "fr" : "en";
  const [gift, setGift] = useState(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem(DRAFT_KEY) || "null");
      if (saved) return saved;
    } catch {
      /* no saved draft */
    }
    return { size: "A4", page_tier: 50, recipient_name: "", message: "", from_name: user?.name || "" };
  });
  const [adding, setAdding] = useState(false);
  const [code, setCode] = useState(params.get("code") || "");
  const [redeeming, setRedeeming] = useState(false);
  const [redeemed, setRedeemed] = useState(null);
  const [codeError, setCodeError] = useState("");
  const set = (patch) => setGift((g) => ({ ...g, ...patch }));

  useEffect(() => {
    if (params.get("code")) document.getElementById("redeem")?.scrollIntoView({ behavior: "smooth" });
  }, [params]);

  const addToCart = async () => {
    if (!user) {
      try {
        sessionStorage.setItem(DRAFT_KEY, JSON.stringify(gift));
      } catch {
        /* the form is just filled in again */
      }
      rememberAfterLogin("/gift");
      nav("/auth");
      return;
    }
    setAdding(true);
    try {
      await addGift({ ...gift, lang });
      try {
        sessionStorage.removeItem(DRAFT_KEY);
      } catch {
        /* nothing saved */
      }
      nav("/cart");
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("gift.error"));
      setAdding(false);
    }
  };

  const redeem = async (e) => {
    e.preventDefault();
    if (!code.trim()) return;
    if (!user) {
      rememberAfterLogin(`/gift?code=${encodeURIComponent(code.trim())}`);
      nav("/auth");
      return;
    }
    setRedeeming(true);
    setCodeError("");
    try {
      const { data } = await api.post("/gift-cards/redeem", { code });
      setRedeemed(data);
    } catch (err) {
      const reason = err?.response?.data?.detail?.reason;
      setCodeError(t(`gift.redeem.errors.${reason || "other"}`, { defaultValue: t("gift.redeem.errors.other") }));
    } finally {
      setRedeeming(false);
    }
  };

  const inputClass = "w-full border border-ink/20 p-3 text-sm bg-white focus:border-[color:var(--ink)] focus:outline-none";
  const choice = (on) =>
    `px-5 py-3 border transition-colors ${on ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]" : "border-ink/30 hover:border-[color:var(--ink)]"}`;

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
      <div className="max-w-[1100px] mx-auto">
        <div className="mb-12 max-w-2xl">
          <div className="eyebrow mb-3">{t("gift.eyebrow")}</div>
          <h1 className="font-serif-display text-4xl md:text-6xl tracking-tight mb-4">{t("gift.title")}</h1>
          <p className="text-ink/70">{t("gift.subtitle")}</p>
          <a href="#redeem" className="inline-block mt-4 text-sm underline text-ink/80 hover:text-[color:var(--coral)]">{t("gift.haveCode")}</a>
        </div>

        <div className="grid md:grid-cols-2 gap-12 mb-24">
          <div>
            <div className="eyebrow mb-4">{t("createAlbum.format.size")}</div>
            <div className="flex gap-3 mb-8">
              {["A4", "A5"].map((s) => (
                <button key={s} type="button" onClick={() => set({ size: s })} className={choice(gift.size === s)} data-testid={`gift-size-${s}`}>
                  <span className="font-semibold tracking-widest text-sm">{s}</span>
                </button>
              ))}
            </div>
            <div className="eyebrow mb-4">{t("createAlbum.format.pageCount")}</div>
            <div className="flex flex-wrap gap-3 mb-3">
              {PAGE_TIERS.map((tier) => (
                <button key={tier} type="button" onClick={() => set({ page_tier: tier })} className={choice(gift.page_tier === tier)} data-testid={`gift-pages-${tier}`}>
                  <span className="font-semibold tracking-widest text-sm block">{tier}p</span>
                  <span className={`text-xs block mt-0.5 ${gift.page_tier === tier ? "text-paper/80" : "text-ink/75"}`}>
                    ${giftValue(gift.size, tier)}
                  </span>
                </button>
              ))}
            </div>
            <p className="text-xs text-[color:var(--muted)] mb-8">{t("gift.priceNote", { shipping: SHIPPING_PRICE })}</p>

            <div className="space-y-4 mb-8">
              <div>
                <label htmlFor="gift-recipient" className="eyebrow block mb-2">{t("gift.recipient")}</label>
                <input className={inputClass} maxLength={60} value={gift.recipient_name} onChange={(e) => set({ recipient_name: e.target.value })} placeholder={t("gift.recipientPlaceholder")} id="gift-recipient" data-testid="gift-recipient" />
              </div>
              <div>
                <label htmlFor="gift-message" className="eyebrow block mb-2">{t("gift.message")}</label>
                <textarea className={`${inputClass} h-24 resize-none`} maxLength={300} value={gift.message} onChange={(e) => set({ message: e.target.value })} placeholder={t("gift.messagePlaceholder")} id="gift-message" data-testid="gift-message" />
                <p className="text-[11px] text-[color:var(--muted)] text-right">{gift.message.length}/300</p>
              </div>
              <div>
                <label htmlFor="gift-from" className="eyebrow block mb-2">{t("gift.from")}</label>
                <input className={inputClass} maxLength={60} value={gift.from_name} onChange={(e) => set({ from_name: e.target.value })} id="gift-from" data-testid="gift-from" />
              </div>
            </div>

            <div className="flex items-center justify-between border-t border-[color:var(--border-soft)] pt-5 mb-5">
              <span className="font-medium">{t("gift.cardPrice")}</span>
              <span className="text-xl font-medium" data-testid="gift-price">${giftValue(gift.size, gift.page_tier).toFixed(2)}</span>
            </div>
            {/* Bought online only: until Whish Pay / card (ONLINE_PAYMENT),
                "coming soon" — a card already received can still be used below. */}
            <button
              type="button"
              onClick={addToCart}
              disabled={adding || !ONLINE_PAYMENT}
              className="w-full inline-flex items-center justify-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] py-4 hover:bg-[color:var(--coral)] transition-colors text-sm font-semibold tracking-widest uppercase disabled:opacity-60 disabled:hover:bg-[color:var(--ink)] disabled:cursor-not-allowed"
              data-testid="gift-add-btn"
            >
              {adding && <Loader2 size={14} className="animate-spin" />}
              {ONLINE_PAYMENT ? t("cart.add") : t("cart.payment.soon")}
            </button>
            <p className={`text-xs mt-3 ${ONLINE_PAYMENT ? "text-[color:var(--muted)]" : "text-[color:var(--coral)]"}`} data-testid="gift-soon">
              {ONLINE_PAYMENT ? t("gift.pdfNote") : t("gift.soon")}
            </p>
          </div>

          <div className="md:sticky md:top-24 h-fit">
            <div className="eyebrow mb-4">{t("gift.preview")}</div>
            <GiftCardPreview gift={gift} lang={lang} />
          </div>
        </div>

        {/* A card received: its code. */}
        <section id="redeem" className="border-t border-[color:var(--border-soft)] pt-16 max-w-xl scroll-mt-24">
          <div className="eyebrow mb-3">{t("gift.redeem.eyebrow")}</div>
          <h2 className="font-serif-display text-3xl md:text-4xl tracking-tight mb-3">{t("gift.redeem.title")}</h2>
          <p className="text-ink/70 mb-6">{t("gift.redeem.subtitle")}</p>
          {redeemed ? (
            <div className="border border-[color:var(--ink)] bg-white p-6" data-testid="gift-redeemed">
              <p className="font-serif-display text-2xl mb-2">{t("gift.redeem.done", { from: redeemed.gift_card.from_name, context: redeemed.gift_card.from_name ? "from" : undefined })}</p>
              <p className="text-sm text-ink/75 mb-5">
                {t("gift.redeem.doneBody", {
                  size: redeemed.gift_card.size,
                  pages: redeemed.gift_card.page_tier,
                  credit: (redeemed.credit_balance_cents / 100).toFixed(2),
                })}
              </p>
              <Link to="/choose-template" className="inline-block bg-[color:var(--ink)] text-[color:var(--paper)] px-6 py-3 text-sm font-semibold tracking-widest uppercase hover:bg-[color:var(--coral)] transition-colors" data-testid="gift-create-album">
                {t("gift.redeem.create")}
              </Link>
            </div>
          ) : (
            <form onSubmit={redeem} className="flex flex-col sm:flex-row gap-3">
              <input
                className={`${inputClass} font-mono uppercase tracking-widest ${codeError ? "border-red-500" : ""}`}
                value={code}
                onChange={(e) => {
                  setCode(e.target.value);
                  setCodeError("");
                }}
                placeholder="EVER-XXXX-XXXX"
                autoComplete="off"
                data-testid="gift-code"
              />
              <button type="submit" disabled={redeeming || !code.trim()} className="shrink-0 inline-flex items-center justify-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] px-6 py-3 text-sm font-semibold tracking-widest uppercase hover:bg-[color:var(--coral)] transition-colors disabled:opacity-60" data-testid="gift-redeem-btn">
                {redeeming && <Loader2 size={14} className="animate-spin" />}
                {t("gift.redeem.use")}
              </button>
            </form>
          )}
          {codeError && <p className="text-sm text-red-600 mt-2" data-testid="gift-code-error">{codeError}</p>}
        </section>
      </div>
    </main>
  );
}

/** The card as the PDF will show it (same layout as render_gift_card_pdf). */
export function GiftCardPreview({ gift, lang, code = "EVER-XXXX-XXXX" }) {
  const { t } = useTranslation();
  const tl = (key, opts) => t(key, { ...opts, lng: lang });
  const until = new Date(Date.now() + 365 * 24 * 3600 * 1000).toLocaleDateString(lang === "fr" ? "fr-FR" : "en-US", { day: "numeric", month: "long", year: "numeric" });
  // Sizes in % of the card's width (cqw), as on the PDF (A6 landscape).
  return (
    <div className="relative bg-[#F7F3EB] shadow-md aspect-[148/105] w-full overflow-hidden" style={{ containerType: "inline-size" }} data-testid="gift-preview">
      <div className="absolute inset-y-0 left-0 w-[2.4%] bg-[color:var(--coral)]" />
      {/* The four albums of the home page, on the right. */}
      <img src="/hero-shelf-v2-380.webp" alt="" width={380} height={512} className="absolute right-[5.2%] top-[7.4%] h-[85.2%] w-auto" />
      <div className="absolute left-[6.7%] w-[39.5%] top-[6%] bottom-[7%] flex flex-col">
        <span className="font-serif-display font-semibold leading-none" style={{ fontSize: "4.8cqw" }}>Everbook</span>
        <span className="font-semibold text-[color:var(--coral)] tracking-wider mt-[2%]" style={{ fontSize: "1.7cqw" }}>{tl("gift.card.eyebrow")}</span>
        <p className="font-serif-display font-semibold mt-[6%] leading-tight" style={{ fontSize: "3.6cqw" }}>
          {gift.recipient_name ? tl("gift.card.for", { name: gift.recipient_name }) : tl("gift.card.forAnonymous")}
        </p>
        {gift.message && (
          <p className="font-serif-display mt-[2%] leading-snug line-clamp-4" style={{ fontSize: "2.4cqw" }}>
            {lang === "fr" ? `« ${gift.message} »` : `“${gift.message}”`}
          </p>
        )}
        {gift.from_name && <p className="font-serif-display text-right" style={{ fontSize: "2.4cqw" }}>— {gift.from_name}</p>}
        <div className="mt-auto">
          <p className="text-[color:var(--muted)] leading-snug" style={{ fontSize: "1.55cqw" }}>{tl("gift.card.what", { size: gift.size, pages: gift.page_tier })}</p>
          <div className="border border-[color:var(--ink)] mt-[3%] px-[4%] py-[2.5%]">
            <p className="text-[color:var(--muted)] font-semibold" style={{ fontSize: "1.45cqw" }}>{tl("gift.card.code")}</p>
            <p className="font-semibold tracking-wide whitespace-nowrap" style={{ fontSize: "3.5cqw" }}>{code}</p>
          </div>
          <p className="text-[color:var(--muted)] mt-[3%] leading-snug" style={{ fontSize: "1.55cqw" }}>{tl("gift.card.how")}</p>
          <p className="text-[color:var(--muted)]" style={{ fontSize: "1.55cqw" }}>{tl("gift.card.valid", { date: until })}</p>
        </div>
      </div>
    </div>
  );
}
