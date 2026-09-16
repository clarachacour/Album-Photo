import React, { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Trans, useTranslation } from "react-i18next";
import { useAuth } from "@/lib/auth";
import { Loader2 } from "lucide-react";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const { forgotPassword } = useAuth();
  const { t } = useTranslation();

  const submit = async (e) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      await forgotPassword(email.trim().toLowerCase());
      setSent(true);
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("auth.forgot.error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center p-8 bg-[color:var(--paper)]">
      <div className="w-full max-w-md">
        <Link to="/auth" className="eyebrow inline-block mb-8 text-[color:var(--muted)] hover:text-[color:var(--ink)] transition-colors">
          ← {t("auth.backToSignIn")}
        </Link>
        <h1 className="font-serif-display text-5xl tracking-tight mb-3">{t("auth.forgot.title")}</h1>
        <p className="text-[color:var(--ink)]/70 mb-10">{t("auth.forgot.subtitle")}</p>

        {sent ? (
          <div className="border border-[color:var(--border-soft)] p-6 text-sm text-[color:var(--ink)]/80">
            <Trans i18nKey="auth.forgot.sentMessage" values={{ email }} components={{ 1: <strong /> }} />
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-5">
            <div>
              <label className="eyebrow block mb-2">{t("auth.email")}</label>
              <input
                id="forgot-email"
                name="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full bg-transparent border-0 border-b border-[color:var(--ink)]/30 focus:border-[color:var(--ink)] focus:outline-none py-3 text-lg font-serif-display"
              />
            </div>
            <button
              type="submit"
              disabled={busy}
              className="mt-6 inline-flex items-center justify-center gap-3 bg-[color:var(--ink)] text-[color:var(--paper)] px-10 py-4 hover:bg-[color:var(--coral)] transition-colors disabled:opacity-60"
            >
              {busy && <Loader2 size={16} className="animate-spin" />}
              <span className="text-sm font-semibold tracking-widest uppercase">{t("auth.forgot.submit")}</span>
            </button>
          </form>
        )}
      </div>
    </main>
  );
}
