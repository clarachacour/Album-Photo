import React, { createContext, useContext, useEffect, useState } from "react";
import { api } from "./api";
import i18n from "@/lib/i18n";

const AuthContext = createContext(null);
const SIGNED_IN_BEFORE = "everbook_signed_in_before";

function saveSession(data) {
  localStorage.setItem("album_token", data.token);
  localStorage.setItem("album_user", JSON.stringify(data.user));
  try {
    localStorage.setItem(SIGNED_IN_BEFORE, "1");
  } catch {
    /* storage unavailable */
  }
}

/** Someone who already has an account on this device: the sign-in page
 * then opens on "Welcome back" rather than on creating an account. */
export function hasSignedInBefore() {
  try {
    return Boolean(
      localStorage.getItem(SIGNED_IN_BEFORE) || localStorage.getItem("album_user") || localStorage.getItem("saved_user_email")
    );
  } catch {
    return false;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const raw = localStorage.getItem("album_user");
    return raw ? JSON.parse(raw) : null;
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("album_token");
    // The print page (opened by the server to make the PDF) runs on a key
    // that only opens one album, not a login: checking it here would be
    // refused and the 401 would erase the key the page is using.
    if (!token || window.location.pathname.startsWith("/print/")) {
      setLoading(false);
      return;
    }
    api
      .get("/auth/me")
      .then((r) => {
        setUser(r.data);
        localStorage.setItem("album_user", JSON.stringify(r.data));
      })
      .catch(() => {
        localStorage.removeItem("album_token");
        localStorage.removeItem("album_user");
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    saveSession(data);
    setUser(data.user);
    return data.user;
  };

  const signup = async (name, email, password) => {
    const lang = (i18n.language || "en").startsWith("fr") ? "fr" : "en";
    const { data } = await api.post("/auth/signup", { name, email, password, lang });
    saveSession(data);
    setUser(data.user);
    return data.user;
  };

  const logout = () => {
    localStorage.removeItem("album_token");
    localStorage.removeItem("album_user");
    setUser(null);
  };

  const loginWithGoogle = async (credential) => {
    const { data } = await api.post("/auth/google", { credential });
    saveSession(data);
    setUser(data.user);
    return data.user;
  };

  const loginWithApple = async (idToken, name) => {
    const { data } = await api.post("/auth/apple", { id_token: idToken, name });
    saveSession(data);
    setUser(data.user);
    return data.user;
  };

  const forgotPassword = async (email) => {
    const { data } = await api.post("/auth/forgot-password", { email });
    return data;
  };

  const resetPassword = async (token, newPassword) => {
    const { data } = await api.post("/auth/reset-password", { token, new_password: newPassword });
    return data;
  };

  const updateUser = (nextUser) => {
    localStorage.setItem("album_user", JSON.stringify(nextUser));
    setUser(nextUser);
  };

  // Only ever meaningful for a classic (email/password) signup that
  // hasn't verified yet — the backend itself is a no-op for anyone
  // already verified (Google/Apple accounts included), so this is safe
  // to call without checking user.email_verified first.
  const resendVerification = async () => {
    const { data } = await api.post("/auth/resend-verification");
    return data;
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout, loginWithGoogle, loginWithApple, forgotPassword, resetPassword, updateUser, resendVerification }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
