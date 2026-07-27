import React, { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import { Loader2 } from "lucide-react";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const { resetPassword } = useAuth();
  const nav = useNavigate();

  const submit = async (e) => {
    e.preventDefault();
    if (busy) return;
    if (!token) {
      toast.error("This reset link is missing its token — please request a new one.");
      return;
    }
    setBusy(true);
    try {
      await resetPassword(token, password);
      toast.success("Password updated — you can sign in now.");
      nav("/auth");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "This link is invalid or has expired");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center p-8 bg-[color:var(--paper)]">
      <div className="w-full max-w-md">
        <Link to="/auth" className="eyebrow inline-block mb-8 text-[color:var(--muted)] hover:text-[color:var(--ink)] transition-colors">
          ← Back to sign in
        </Link>
        <h1 className="font-serif-display text-5xl tracking-tight mb-3">Set a new password.</h1>
        <p className="text-[color:var(--ink)]/70 mb-10">Choose a new password for your account.</p>

        {!token && (
          <p className="text-sm text-red-600 mb-6">
            This link is missing its reset token. Please request a new one from the sign-in page.
          </p>
        )}

        <form onSubmit={submit} className="space-y-5">
          <div>
            <label className="eyebrow block mb-2">New password</label>
            <input
              id="reset-password"
              name="new-password"
              type="password"
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
            <span className="text-sm font-semibold tracking-widest uppercase">Update password</span>
          </button>
        </form>
      </div>
    </main>
  );
}