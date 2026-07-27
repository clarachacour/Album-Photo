import React, { useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

const GOOGLE_CLIENT_ID = process.env.REACT_APP_GOOGLE_CLIENT_ID;
const APPLE_CLIENT_ID = process.env.REACT_APP_APPLE_CLIENT_ID;
const APPLE_REDIRECT_URI = process.env.REACT_APP_APPLE_REDIRECT_URI;

function loadScript(src, id) {
  return new Promise((resolve, reject) => {
    if (document.getElementById(id)) return resolve();
    const script = document.createElement("script");
    script.src = src;
    script.id = id;
    script.async = true;
    script.onload = resolve;
    script.onerror = reject;
    document.body.appendChild(script);
  });
}

export default function SocialAuthButtons() {
  const { loginWithGoogle, loginWithApple } = useAuth();
  const googleBtnRef = useRef(null);
  const [appleReady, setAppleReady] = useState(false);
  const nav = useNavigate();

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return;
    loadScript("https://accounts.google.com/gsi/client", "google-identity-script")
      .then(() => {
        if (!window.google || !googleBtnRef.current) return;
        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: async (response) => {
            try {
              await loginWithGoogle(response.credential);
              toast.success("Welcome!");
              nav("/dashboard");
            } catch (err) {
              toast.error(err?.response?.data?.detail || "Google sign-in failed");
            }
          },
        });
        window.google.accounts.id.renderButton(googleBtnRef.current, {
          theme: "outline",
          size: "large",
          width: 320,
          text: "continue_with",
        });
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!APPLE_CLIENT_ID || !APPLE_REDIRECT_URI) return;
    loadScript(
      "https://appleid.cdn-apple.com/appleauth/static/jsapi/appleid/1/en_US/appleid.auth.js",
      "apple-identity-script"
    )
      .then(() => {
        if (!window.AppleID) return;
        window.AppleID.auth.init({
          clientId: APPLE_CLIENT_ID,
          scope: "name email",
          redirectURI: APPLE_REDIRECT_URI,
          usePopup: true,
        });
        setAppleReady(true);
      })
      .catch(() => {});
  }, []);

  const handleAppleClick = async () => {
    try {
      const res = await window.AppleID.auth.signIn();
      const idToken = res.authorization?.id_token;
      const fullName = res.user?.name ? `${res.user.name.firstName || ""} ${res.user.name.lastName || ""}`.trim() : undefined;
      if (!idToken) throw new Error("No id_token returned");
      await loginWithApple(idToken, fullName);
      toast.success("Welcome!");
      nav("/dashboard");
    } catch (err) {
      if (err?.error === "popup_closed_by_user") return;
      toast.error(err?.response?.data?.detail || "Apple sign-in failed");
    }
  };

  if (!GOOGLE_CLIENT_ID && !(APPLE_CLIENT_ID && APPLE_REDIRECT_URI)) return null;

  return (
    <div className="space-y-3">
      {GOOGLE_CLIENT_ID && <div ref={googleBtnRef} data-testid="google-signin-button" />}
      {appleReady && (
        <button
          type="button"
          onClick={handleAppleClick}
          data-testid="apple-signin-button"
          className="w-full inline-flex items-center justify-center gap-3 border border-[color:var(--ink)] py-3 hover:bg-[color:var(--ink)] hover:text-[color:var(--paper)] transition-colors"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M16.365 1.43c0 1.14-.493 2.27-1.177 3.08-.744.9-1.99 1.57-2.987 1.57-.12 0-.23-.02-.3-.03-.01-.06-.04-.22-.04-.39 0-1.15.572-2.27 1.206-2.98.804-.94 2.142-1.64 3.248-1.68.03.13.05.28.05.43zm4.565 15.71c-.03.07-.463 1.58-1.518 3.12-.945 1.34-1.94 2.71-3.43 2.71-1.517 0-1.9-.88-3.63-.88-1.698 0-2.302.91-3.67.91-1.377 0-2.4-1.25-3.386-2.59C4.29 18.4 3 15.86 3 13.47c0-3.9 2.535-5.96 5.03-5.96 1.33 0 2.437.9 3.27.9.795 0 2.037-.96 3.535-.96.573 0 2.628.05 3.985 2 -.104.065-2.378 1.39-2.378 4.26 0 3.42 3.001 4.63 3.033 4.64z" />
          </svg>
          <span className="text-sm font-semibold tracking-widest uppercase">Continue with Apple</span>
        </button>
      )}
      <div className="flex items-center gap-3 py-1">
        <div className="flex-1 h-px bg-[color:var(--border-soft)]" />
        <span className="eyebrow text-[color:var(--muted)]">or</span>
        <div className="flex-1 h-px bg-[color:var(--border-soft)]" />
      </div>
    </div>
  );
}