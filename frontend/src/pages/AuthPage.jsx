import React, { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import { TID } from "@/constants/testIds";
import { CoverMockup } from "@/components/CoverPreview";
import { DEFAULT_COVER, defaultLogoItem } from "@/lib/coverTemplates";
import SocialAuthButtons from "@/components/SocialAuthButtons";
import { Loader2 } from "lucide-react";

export default function AuthPage() {
  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [busy, setBusy] = useState(false);
  const { login, signup } = useAuth();
  const nav = useNavigate();

  // Pre-fill the email if the user previously checked "Remember me"
  // (only the email is stored — never the password; the browser's own
  // password manager handles the rest via the autoComplete attributes below).
  useEffect(() => {
    const savedEmail = localStorage.getItem("saved_user_email");
    if (savedEmail) {
      setEmail(savedEmail);
      setRememberMe(true);
    }
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);

    if (rememberMe) {
      localStorage.setItem("saved_user_email", email.trim().toLowerCase());
    } else {
      localStorage.removeItem("saved_user_email");
    }

    try {
      if (mode === "signup") {
        await signup(name.trim(), email.trim().toLowerCase(), password);
        toast.success("Welcome!");
      } else {
        await login(email.trim().toLowerCase(), password);
        toast.success("Welcome back!");
      }
      nav("/dashboard");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "An error occurred");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen grid grid-cols-1 md:grid-cols-2">
      {/* Left: form */}
      <div className="flex items-center justify-center p-8 md:p-16 bg-[color:var(--paper)]">
        <div className="w-full max-w-md">
          <Link to="/" className="eyebrow inline-block mb-8 text-[color:var(--muted)] hover:text-[color:var(--ink)] transition-colors">
            ← Back
          </Link>
          <h1 className="font-serif-display text-5xl md:text-6xl tracking-tight mb-3">
            {mode === "login" ? "Welcome back !" : "Create your first edition."}
          </h1>
          <p className="text-[color:var(--ink)]/70 mb-8">
            {mode === "login"
              ? "Sign in to access your albums."
              : "One account to create, save, and export."}
          </p>

          {/* Google / Apple sign-in (hidden automatically if not configured) */}
          <SocialAuthButtons />

          <form onSubmit={submit} className="space-y-5">
            {mode === "signup" && (
              <div>
                <label className="eyebrow block mb-2">Name</label>
                <input
                  data-testid={TID.authNameInput}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  autoComplete="name"
                  className="w-full bg-transparent border-0 border-b border-[color:var(--ink)]/30 focus:border-[color:var(--ink)] focus:outline-none py-3 text-lg font-serif-display"
                />
              </div>
            )}
            <div>
              <label className="eyebrow block mb-2">Email</label>
              <input
                data-testid={TID.authEmailInput}
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="username"
                className="w-full bg-transparent border-0 border-b border-[color:var(--ink)]/30 focus:border-[color:var(--ink)] focus:outline-none py-3 text-lg font-serif-display"
              />
            </div>
            <div>
              <label className="eyebrow block mb-2">Password</label>
              <input
                data-testid={TID.authPasswordInput}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
                autoComplete={mode === "signup" ? "new-password" : "current-password"}
                className="w-full bg-transparent border-0 border-b border-[color:var(--ink)]/30 focus:border-[color:var(--ink)] focus:outline-none py-3 text-lg font-serif-display"
              />
            </div>

            {/* Remember Me & Forgot Password */}
            {mode === "login" && (
              <div className="flex items-center justify-between text-sm pt-2">
                <label className="flex items-center gap-2 cursor-pointer text-[color:var(--ink)]/80">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                    className="accent-[color:var(--ink)]"
                  />
                  Remember me
                </label>
                <button
                  type="button"
                  onClick={() => nav("/forgot-password")}
                  data-testid={TID.authForgotPassword}
                  className="text-xs text-[color:var(--muted)] hover:text-[color:var(--ink)] underline transition-colors"
                >
                  Forgot password?
                </button>
              </div>
            )}

            <button
              type="submit"
              data-testid={TID.authSubmit}
              disabled={busy}
              className="mt-6 w-full md:w-auto inline-flex items-center justify-center gap-3 bg-[color:var(--ink)] text-[color:var(--paper)] px-10 py-4 hover:bg-[color:var(--coral)] transition-colors disabled:opacity-60"
            >
              {busy && <Loader2 size={16} className="animate-spin" />}
              <span className="text-sm font-semibold tracking-widest uppercase">
                {mode === "login" ? "Sign in" : "Create account"}
              </span>
            </button>
          </form>

          <button
            data-testid={TID.authToggle}
            onClick={() => setMode(mode === "login" ? "signup" : "login")}
            className="mt-8 text-sm text-[color:var(--muted)] hover:text-[color:var(--ink)] underline underline-offset-4 transition-colors"
          >
            {mode === "login" ? "Don't have an account? Sign up" : "Already have an account? Sign in"}
          </button>
        </div>
      </div>

      {/* Right: art */}
      <div className="hidden md:flex bg-[color:var(--editor-canvas)] items-center justify-center p-16 relative overflow-hidden">
        <div className="absolute inset-0 grain" />
        <div className="relative max-w-md w-full">
          <CoverMockup cover={{ ...DEFAULT_COVER, extra_items: [defaultLogoItem()] }} title="Western Australia" year={2026} country="Australia" />
        </div>
      </div>
    </main>
  );
}