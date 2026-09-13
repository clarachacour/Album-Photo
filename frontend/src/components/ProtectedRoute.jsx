import React from "react";
import { Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/lib/auth";

export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  const { t } = useTranslation();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[color:var(--paper)]">
        <p className="eyebrow animate-slow-pulse">{t("common.loading")}</p>
      </div>
    );
  }
  if (!user) return <Navigate to="/auth" replace />;
  return children;
}
