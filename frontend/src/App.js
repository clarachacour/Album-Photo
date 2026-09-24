import React from "react"; 
import "@/App.css"; 
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { Toaster } from "sonner";

import { AuthProvider } from "@/lib/auth";
import ProtectedRoute from "@/components/ProtectedRoute";
import TopNav from "@/components/TopNav";
import Footer from "@/components/Footer";
import Landing from "@/pages/Landing";
import AuthPage from "@/pages/AuthPage";
import Dashboard from "@/pages/Dashboard";
import CreateAlbum from "@/pages/CreateAlbum";
import ChooseTemplate from "@/pages/ChooseTemplate";
import AlbumEditor from "@/pages/AlbumEditor";

// 🆕 Imports des deux nouvelles pages
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";
import MobileUpload from "@/pages/MobileUpload";
import PrintAlbum from "@/pages/PrintAlbum";
import AccountPage from "@/pages/AccountPage";
import OrdersPage from "@/pages/OrdersPage";
import OrderDetailPage from "@/pages/OrderDetailPage";
import OrderFeedback from "@/pages/OrderFeedback";
import OrderCheckoutPage from "@/pages/OrderCheckoutPage";
import AdminOrdersPage from "@/pages/AdminOrdersPage";
import FAQPage from "@/pages/FAQPage";
import ContactPage from "@/pages/ContactPage";
import VerifyEmailPending from "@/pages/VerifyEmailPending";
import TermsPage from "@/pages/TermsPage";
import PrivacyPage from "@/pages/PrivacyPage";
import ReturnsPage from "@/pages/ReturnsPage";
import ShippingPage from "@/pages/ShippingPage";

function AppChrome({ children }) {
  const location = useLocation();
  const isPrintRoute = location.pathname.startsWith("/print/");
  if (isPrintRoute) return children;
  return (
    <>
      <TopNav />
      {children}
      <Footer />
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

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <AppChrome>
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
            <Route
              path="/editor/:id"
              element={
                <ProtectedRoute>
                  <AlbumEditor />
                </ProtectedRoute>
              }
            />
          </Routes>
          </AppChrome>
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
