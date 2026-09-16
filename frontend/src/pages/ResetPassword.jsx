import React, { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/lib/auth";
import PasswordInput from "@/components/PasswordInput";
import { Loader2 } from "lucide-react";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const { resetPassword } = useAuth();
  const { t } = useTranslation();
  const nav = useNavigate();

  const submit = async (e) => {
    e.preventDefault();
    if (busy) return;
    if (!token) {
      toast.error(t("auth.reset.missingTokenToast"));
      return;
    }
    setBusy(true);
    try {
      await resetPassword(token, password);
      toast.success(t("auth.reset.successToast"));
      nav("/auth");
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("auth.reset.error"));
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
        <h1 className="font-serif-display text-5xl tracking-tight mb-3">{t("auth.reset.title")}</h1>
        <p className="text-[color:var(--ink)]/70 mb-10">{t("auth.reset.subtitle")}</p>

        {!token && (
          <p className="text-sm text-red-600 mb-6">
            {t("auth.reset.missingToken")}
          </p>
        )}

        <form onSubmit={submit} className="space-y-5">
          <div>
            <label className="eyebrow block mb-2">{t("auth.reset.newPassword")}</label>
            <PasswordInput
              id="reset-password"
              name="new-password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
              className="w-full bg-transparent border-0 border-b border-[color:var(--ink)]/30 focus:border-[color:var(--ink)] focus:outline-none py-3 text-lg font-serif-display"
            />
          </div>
          <button
            type="submit"
            disabled={busy || !token}
            className="mt-6 inline-flex items-center justify-center gap-3 bg-[color:var(--ink)] text-[color:var(--paper)] px-10 py-4 hover:bg-[color:var(--coral)] transition-colors disabled:opacity-60"
          >
            {busy && <Loader2 size={16} className="animate-spin" />}
            <span className="text-sm font-semibold tracking-widest uppercase">{t("auth.reset.submit")}</span>
          </button>
        </form>
      </div>
    </main>
  );
}
