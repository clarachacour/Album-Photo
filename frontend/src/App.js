import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";

import { AuthProvider } from "@/lib/auth";
import ProtectedRoute from "@/components/ProtectedRoute";
import TopNav from "@/components/TopNav";
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

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <TopNav />
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/auth" element={<AuthPage />} />

            {/* 🆕 Nouvelles routes publiques pour le mot de passe */}
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/mobile-upload/:token" element={<MobileUpload />} />

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
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;