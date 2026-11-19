import React, { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CheckCircle2, Clock, Loader2, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useCart } from "@/lib/cart";
import { usePageMeta } from "@/hooks/usePageMeta";

// How often, and how long, the page asks where the payment stands. Whish's
// confirmation usually lands within seconds; past this, the customer is
// told it's still being checked (the server keeps checking on its own).
const ASK_EVERY_MS = 3000;
const ASK_FOR_MS = 3 * 60 * 1000;

/**
 * Back from Whish Pay (/payment/return?payment=…&outcome=…), or from the
 * card form (…&via=card): the server checks the payment with Whish or the
 * bank (GET /payments/:id) — the "outcome" in the
 * address is only where Whish sent the customer, never trusted on its own.
 * Paid: the cart was ordered. Failed: nothing ordered, the cart is still
 * there to try again.
 */
export default function PaymentReturnPage() {
  usePageMeta("paymentReturn");
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const paymentId = params.get("payment");
  // Where Whish sent the customer back: "failure" helps the server close a
  // failed attempt at once (it still asks Whish whether it was paid).
  const outcome = params.get("outcome") === "failure" ? "failure" : "";
  // Paid by card (the cart adds via=card): the texts name the bank, not
  // Whish, even before the first answer.
  const viaCard = params.get("via") === "card";
  const { refresh } = useCart();
  const [payment, setPayment] = useState(null);
  const [gaveUp, setGaveUp] = useState(false);
  const [error, setError] = useState(false);
  const started = useRef(Date.now());

  useEffect(() => {
    if (!paymentId) return undefined;
    let stop = false;
    let timer;
    const ask = async () => {
      try {
        const { data } = await api.get(`/payments/${paymentId}`, { params: outcome ? { outcome } : {} });
        if (stop) return;
        setPayment(data);
        if (data.status !== "pending" && data.status !== "placing") {
          refresh();
          return;
        }
      } catch (err) {
        if (stop) return;
        if (err?.response?.status === 404) {
          setError(true);
          return;
        }
      }
      if (Date.now() - started.current > ASK_FOR_MS) {
        setGaveUp(true);
        return;
      }
      timer = setTimeout(ask, ASK_EVERY_MS);
    };
    ask();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
    // Once per payment.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paymentId]);

  const status = error || !paymentId ? "unknown" : payment?.status || "pending";
  const waiting = (status === "pending" || status === "placing") && !gaveUp;
  const orders = payment?.orders || [];
  const cards = payment?.gift_cards || [];

  const card = payment?.provider ? payment.provider === "card" : viaCard;
  let Icon = Loader2;
  let title = t("paymentReturn.checking");
  let body = t(card ? "paymentReturn.checkingBodyCard" : "paymentReturn.checkingBody");
  if (status === "placed") {
    Icon = CheckCircle2;
    title = t("paymentReturn.paid");
    body = cards.length && !orders.length ? t("paymentReturn.paidGifts") : t("paymentReturn.paidBody");
  } else if (status === "failed" || status === "expired" || status === "not_started") {
    Icon = XCircle;
    title = t("paymentReturn.failed");
    body = t("paymentReturn.failedBody");
  } else if (status === "needs_review") {
    Icon = Clock;
    title = t("paymentReturn.review");
    body = t("paymentReturn.reviewBody");
  } else if (status === "unknown") {
    Icon = XCircle;
    title = t("paymentReturn.unknown");
    body = t("paymentReturn.unknownBody");
  } else if (gaveUp) {
    Icon = Clock;
    title = t(card ? "paymentReturn.slowCard" : "paymentReturn.slow");
    body = t(card ? "paymentReturn.slowBodyCard" : "paymentReturn.slowBody");
  }

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12 flex items-center justify-center">
      <div className="max-w-[520px] mx-auto text-center" data-testid="payment-return" data-status={status}>
        <Icon
          className={`w-8 h-8 mx-auto mb-6 ${waiting ? "animate-spin text-[color:var(--muted)]" : status === "placed" ? "text-emerald-700" : "text-[color:var(--coral-text)]"}`}
          aria-hidden="true"
        />
        <h1 className="font-serif-display text-4xl md:text-5xl tracking-tight mb-4" aria-live="polite">{title}</h1>
        <p className="text-ink/70 mb-8">{body}</p>
        {status === "placed" && cards.length > 0 && (
          <ul className="text-sm mb-8 space-y-1" data-testid="payment-gift-codes">
            {cards.map((c) => (
              <li key={c.id}>{t("paymentReturn.giftCode")} <strong className="tracking-wider">{c.code}</strong></li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap items-center justify-center gap-4">
          {(status === "placed" || status === "needs_review" || gaveUp) && (
            <Link
              to="/orders"
              className="inline-flex items-center justify-center bg-[color:var(--ink)] text-[color:var(--paper)] px-8 py-3 hover:bg-[color:var(--coral)] transition-colors text-sm font-semibold tracking-widest uppercase"
              data-testid="payment-to-orders"
            >
              {t("paymentReturn.toOrders")}
            </Link>
          )}
          {(status === "failed" || status === "expired" || status === "not_started" || status === "unknown") && (
            <Link
              to="/cart"
              className="inline-flex items-center justify-center bg-[color:var(--ink)] text-[color:var(--paper)] px-8 py-3 hover:bg-[color:var(--coral)] transition-colors text-sm font-semibold tracking-widest uppercase"
              data-testid="payment-to-cart"
            >
              {t("paymentReturn.toCart")}
            </Link>
          )}
        </div>
      </div>
    </main>
  );
}
