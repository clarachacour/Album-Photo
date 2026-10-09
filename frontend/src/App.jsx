import React, { Suspense, useEffect } from "react";
import "@/App.css"; 
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "sonner";

import { AuthProvider } from "@/lib/auth";
import { ConfirmProvider } from "@/components/ConfirmDialog";
import ProtectedRoute from "@/components/ProtectedRoute";
import TopNav from "@/components/TopNav";
import Footer from "@/components/Footer";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { lazyPage } from "@/lib/lazyPage";
import { showPendingFlash } from "@/lib/flash";
import { leaveAppBrowser } from "@/lib/inAppBrowser";
import { InAppBrowserBanner } from "@/components/OpenInBrowser";
// Public pages: part of the main code, not downloaded on demand. They are
// also generated as HTML at build time (see prerender.jsx), and the page the
// browser then draws is the same one, straight away, with no blank moment.
import Landing from "@/pages/Landing";
import FAQPage from "@/pages/FAQPage";
import ContactPage from "@/pages/ContactPage";
import TermsPage from "@/pages/TermsPage";
import PrivacyPage from "@/pages/PrivacyPage";
import ReturnsPage from "@/pages/ReturnsPage";
import ShippingPage from "@/pages/ShippingPage";
const AuthPage = lazyPage(() => import("@/pages/AuthPage"));
const Dashboard = lazyPage(() => import("@/pages/Dashboard"));
const CreateAlbum = lazyPage(() => import("@/pages/CreateAlbum"));
const ChooseTemplate = lazyPage(() => import("@/pages/ChooseTemplate"));
const AlbumEditor = lazyPage(() => import("@/pages/AlbumEditor"));

const ForgotPassword = lazyPage(() => import("@/pages/ForgotPassword"));
const ResetPassword = lazyPage(() => import("@/pages/ResetPassword"));
const MobileUpload = lazyPage(() => import("@/pages/MobileUpload"));
const PrintAlbum = lazyPage(() => import("@/pages/PrintAlbum"));
const AccountPage = lazyPage(() => import("@/pages/AccountPage"));
const OrdersPage = lazyPage(() => import("@/pages/OrdersPage"));
const OrderDetailPage = lazyPage(() => import("@/pages/OrderDetailPage"));
const OrderFeedback = lazyPage(() => import("@/pages/OrderFeedback"));
const OrderCheckoutPage = lazyPage(() => import("@/pages/OrderCheckoutPage"));
const AdminOrdersPage = lazyPage(() => import("@/pages/AdminOrdersPage"));
const VerifyEmailPending = lazyPage(() => import("@/pages/VerifyEmailPending"));
const NotFound = lazyPage(() => import("@/pages/NotFound"));

function AppChrome({ children }) {
  const location = useLocation();
  useEffect(() => {
    showPendingFlash();
  }, []);
  const isPrintRoute = location.pathname.startsWith("/print/");
  useEffect(() => {
    if (!isPrintRoute) leaveAppBrowser();
  }, [isPrintRoute]);
  if (isPrintRoute) {
    // The PDF server waits for data-print-ready or data-print-error: a crash
    // is reported at once instead of waiting for its timeout.
    return (
      <ErrorBoundary resetKey={location.pathname} renderFallback={(e) => <div data-print-error="true">{String(e?.message || e)}</div>}>
        {children}
      </ErrorBoundary>
    );
  }
  return (
    <>
      <TopNav />
      <ErrorBoundary resetKey={location.pathname}>{children}</ErrorBoundary>
      <Footer />
      {/* The sign-in page has its own notice, in place of Google's button. */}
      {location.pathname !== "/auth" && <InAppBrowserBanner />}
      <Toaster
        position="top-center"
        toastOptions={{
          style: {
            background: "#1A1A17",
            color: "#F9F8F6",
            border: "none",
            borderRadius: 0,
            fontFamily: "Manrope, sans-serif",
            fontSize: "13px",
            letterSpacing: "0.02em",
          },
        }}
      />
    </>
  );
}

/** Everything inside the router — also used to generate the public pages (prerender.jsx). */
export function AppRoutes() {
  return (
        <AuthProvider>
        <ConfirmProvider>
          <AppChrome>
          {/* Each page's code is downloaded when it's first opened. */}
          <Suspense fallback={<div className="min-h-screen bg-[color:var(--paper)]" />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/auth" element={<AuthPage />} />

            {/* 🆕 Nouvelles routes publiques pour le mot de passe */}
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/mobile-upload/:token" element={<MobileUpload />} />
            <Route path="/print/:id" element={<PrintAlbum />} />
            <Route path="/faq" element={<FAQPage />} />
            <Route path="/contact" element={<ContactPage />} />
            {/* Not wrapped in ProtectedRoute — it IS the destination
                ProtectedRoute redirects an unverified account to, and
                wrapping it would just redirect straight back here. The
                page checks for a session itself and redirects to /auth
                if there isn't one. */}
            <Route path="/verify-email" element={<VerifyEmailPending />} />
            <Route path="/terms" element={<TermsPage />} />
            <Route path="/privacy" element={<PrivacyPage />} />
            <Route path="/returns" element={<ReturnsPage />} />
            <Route path="/shipping" element={<ShippingPage />} />

            <Route
              path="/account"
              element={
                <ProtectedRoute>
                  <AccountPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/orders"
              element={
                <ProtectedRoute>
                  <OrdersPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/orders/:id"
              element={
                <ProtectedRoute>
                  <OrderDetailPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/orders/:id/feedback"
              element={
                <ProtectedRoute>
                  <OrderFeedback />
                </ProtectedRoute>
              }
            />
            <Route
              path="/order/:albumId"
              element={
                <ProtectedRoute>
                  <OrderCheckoutPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/admin/orders"
              element={
                <ProtectedRoute>
                  <AdminOrdersPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <Dashboard />
                </ProtectedRoute>
              }
            />
            <Route
              path="/choose-template"
              element={
                <ProtectedRoute>
                  <ChooseTemplate />
                </ProtectedRoute>
              }
            />
            <Route
              path="/create"
              element={
                <ProtectedRoute>
                  <CreateAlbum />
                </ProtectedRoute>
              }
            />
            {/* Old address of the album-creation form, now at /create. */}
            <Route path="/editor/new" element={<Navigate to="/create" replace />} />
            <Route
              path="/editor/:id"
              element={
                <ProtectedRoute>
                  <AlbumEditor />
                </ProtectedRoute>
              }
            />
            <Route path="*" element={<NotFound />} />
          </Routes>
          </Suspense>
          </AppChrome>
        </ConfirmProvider>
        </AuthProvider>
  );
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </div>
  );
}

export default App;
