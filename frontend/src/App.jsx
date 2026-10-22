import React, { Suspense, useEffect } from "react";
import "@/App.css"; 
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Toaster } from "sonner";

import { AuthProvider } from "@/lib/auth";
import { CartProvider } from "@/lib/cart";
import { ConfirmProvider } from "@/components/ConfirmDialog";
import ProtectedRoute from "@/components/ProtectedRoute";
import TopNav from "@/components/TopNav";
import Footer from "@/components/Footer";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { lazyPage } from "@/lib/lazyPage";
import { showPendingFlash } from "@/lib/flash";
import { leaveAppBrowser } from "@/lib/inAppBrowser";
import { InAppBrowserBanner } from "@/components/OpenInBrowser";
import { setLanguage } from "@/lib/i18n";
import { isPublicPage, localePath, splitLocale } from "@/lib/localePath";
// Public pages: part of the main code, not downloaded on demand. They are
// also generated as HTML at build time (see prerender.jsx), and the page the
// browser then draws is the same one, straight away, with no blank moment.
import Landing from "@/pages/Landing";
import FAQPage from "@/pages/FAQPage";
import ContactPage from "@/pages/ContactPage";
import TermsPage from "@/pages/TermsPage";
import PrivacyPage from "@/pages/PrivacyPage";
import ShippingPage from "@/pages/ShippingPage";
import GiftPage from "@/pages/GiftPage";
import OccasionPage from "@/pages/OccasionPage";
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
const CartPage = lazyPage(() => import("@/pages/CartPage"));
const AdminOrdersPage = lazyPage(() => import("@/pages/AdminOrdersPage"));
const VerifyEmailPending = lazyPage(() => import("@/pages/VerifyEmailPending"));
const PrinterOrderPage = lazyPage(() => import("@/pages/PrinterOrderPage"));
const PrinterDownloadRedirect = lazyPage(() =>
  import("@/pages/PrinterOrderPage").then((m) => ({ default: m.PrinterDownloadRedirect }))
);
const PrinterStatementRedirect = lazyPage(() =>
  import("@/pages/PrinterOrderPage").then((m) => ({ default: m.PrinterStatementRedirect }))
);
const NotFound = lazyPage(() => import("@/pages/NotFound"));

// The public pages' language follows their address: /fr/… is French. A
// visitor reading in French who opens the English address of a public page
// is taken to its French one (search engines, which read in English, stay).
function LocaleSync() {
  const location = useLocation();
  const navigate = useNavigate();
  const { i18n } = useTranslation();
  useEffect(() => {
    const { lng, path } = splitLocale(location.pathname);
    if (lng) {
      if (i18n.resolvedLanguage !== lng) setLanguage(lng);
    } else if (isPublicPage(path) && i18n.resolvedLanguage === "fr") {
      navigate(localePath(path, "fr") + location.search + location.hash, { replace: true });
    }
    // Only when the address changes: the language switcher changes the
    // language first, then the address (reacting to the language alone
    // would switch it straight back).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);
  return null;
}

// The public pages, each in English and, under /fr, in French.
const PUBLIC_ROUTES = [
  ["/", <Landing />],
  ["/faq", <FAQPage />],
  ["/gift", <GiftPage />],
  ["/travel-photo-book", <OccasionPage occasion="travel" />],
  ["/couple-photo-album", <OccasionPage occasion="couple" />],
  ["/family-photo-album", <OccasionPage occasion="family" />],
  ["/contact", <ContactPage />],
  ["/terms", <TermsPage />],
  ["/privacy", <PrivacyPage />],
  ["/shipping", <ShippingPage />],
];

function AppChrome({ children }) {
  const location = useLocation();
  useEffect(() => {
    showPendingFlash();
  }, []);
  const isPrintRoute = location.pathname.startsWith("/print/");
  // A new page opens at its top (the browser keeps the previous page's
  // scroll otherwise, landing halfway down); a link to a section (#…) is
  // left to scroll to it.
  useEffect(() => {
    if (!location.hash) window.scrollTo(0, 0);
  }, [location.pathname, location.hash]);
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
      <LocaleSync />
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
        <CartProvider>
        <ConfirmProvider>
          <AppChrome>
          {/* Each page's code is downloaded when it's first opened. */}
          <Suspense fallback={<div className="min-h-screen bg-[color:var(--paper)]" />}>
          <Routes>
            {PUBLIC_ROUTES.flatMap(([path, element]) => [
              <Route key={path} path={path} element={element} />,
              <Route key={`fr${path}`} path={localePath(path, "fr")} element={element} />,
            ])}
            <Route path="/auth" element={<AuthPage />} />
            {/* Addresses people type by habit. */}
            <Route path="/login" element={<Navigate to="/auth?mode=login" replace />} />
            <Route path="/signin" element={<Navigate to="/auth?mode=login" replace />} />
            <Route path="/signup" element={<Navigate to="/auth?mode=signup" replace />} />
            <Route path="/register" element={<Navigate to="/auth?mode=signup" replace />} />
            {/* Password reset (public) */}
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/mobile-upload/:token" element={<MobileUpload />} />
            <Route path="/print/:id" element={<PrintAlbum />} />
            {/* The print shop's links, from its email (no account). */}
            <Route path="/printer/:orderId" element={<PrinterOrderPage />} />
            <Route path="/printer/:orderId/download" element={<PrinterDownloadRedirect />} />
            <Route path="/everbook-statement" element={<PrinterStatementRedirect />} />
            {/* Not wrapped in ProtectedRoute — it IS the destination
                ProtectedRoute redirects an unverified account to, and
                wrapping it would just redirect straight back here. The
                page checks for a session itself and redirects to /auth
                if there isn't one. */}
            <Route path="/verify-email" element={<VerifyEmailPending />} />

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
              path="/cart"
              element={
                <ProtectedRoute>
                  <CartPage />
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
        </CartProvider>
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
