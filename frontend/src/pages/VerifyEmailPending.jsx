import React, { useState } from "react";
import { Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import { MailCheck, Loader2 } from "lucide-react";

export default function VerifyEmailPending() {
  const { user, loading, logout, resendVerification } = useAuth();
  const { t } = useTranslation();
  const [sending, setSending] = useState(false);

  if (loading) return null;
  // Nothing to gate here if there's no session at all, or if this
  // person's already verified (e.g. they clicked the email link in
  // another tab, then came back to this one) — send them where they'd
  // actually want to be instead of showing a screen that no longer
  // applies to them.
  if (!user) return <Navigate to="/auth" replace />;
  if (user.email_verified !== false) return <Navigate to="/dashboard" replace />;

  const resend = async () => {
    setSending(true);
    try {
      await resendVerification();
      toast.success(t("verifyEmail.resentToast"));
    } catch {
      toast.error(t("verifyEmail.resendError"));
    } finally {
      setSending(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center p-8 bg-[color:var(--paper)]">
      <div className="w-full max-w-md text-center">
        <MailCheck size={32} className="mx-auto mb-6 text-[color:var(--coral)]" />
        <h1 className="font-serif-display text-4xl tracking-tight mb-3">{t("verifyEmail.title")}</h1>
        <p className="text-[color:var(--ink)]/70 mb-2">
          {t("verifyEmail.instructions")}
        </p>
        <p className="font-medium mb-8">{user.email}</p>

        <button
          onClick={resend}
          disabled={sending}
          className="inline-flex items-center justify-center gap-3 bg-[color:var(--ink)] text-[color:var(--paper)] px-8 py-3 hover:bg-[color:var(--coral)] transition-colors disabled:opacity-60"
        >
          {sending && <Loader2 size={16} className="animate-spin" />}
          <span className="text-sm font-semibold tracking-widest uppercase">
            {sending ? t("verifyEmail.sending") : t("verifyEmail.resendButton")}
          </span>
        </button>

        <button
          onClick={logout}
          className="block mx-auto mt-8 text-sm text-[color:var(--muted)] hover:text-[color:var(--ink)] underline underline-offset-4 transition-colors"
        >
          {t("verifyEmail.signOut")}
        </button>
      </div>
    </main>
  );
}
