import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/lib/auth";

export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  const { t } = useTranslation();
  const location = useLocation();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[color:var(--paper)]">
        <p className="eyebrow animate-slow-pulse">{t("common.loading")}</p>
      </div>
    );
  }
  if (!user) return <Navigate to="/auth" replace />;
  // A classic (email/password) signup that hasn't clicked its
  // verification link yet — email_verified is explicitly false only for
  // that case (see AuthProvider/backend/app/routers/auth.py's signup); every Google/Apple
  // account and every account that existed before this feature shipped
  // has it as true or entirely absent, so this never touches them. The
  // check happens here, before any protected page ever mounts, so a
  // still-unverified person never gets far enough to trigger the API
  // calls those pages would otherwise make (which the backend would
  // reject anyway — see get_current_user — but this keeps the redirect a
  // deliberate, visible step instead of a page that half-loads then errors).
  if (user.email_verified === false && location.pathname !== "/verify-email") {
    return <Navigate to="/verify-email" replace />;
  }
  return children;
}
