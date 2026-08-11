import React, { createContext, useContext, useEffect, useState } from "react";
import { api } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const raw = localStorage.getItem("album_user");
    return raw ? JSON.parse(raw) : null;
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("album_token");
    if (!token) {
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
    localStorage.setItem("album_token", data.token);
    localStorage.setItem("album_user", JSON.stringify(data.user));
    setUser(data.user);
    return data.user;
  };

  const signup = async (name, email, password) => {
    const { data } = await api.post("/auth/signup", { name, email, password });
    localStorage.setItem("album_token", data.token);
    localStorage.setItem("album_user", JSON.stringify(data.user));
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
    localStorage.setItem("album_token", data.token);
    localStorage.setItem("album_user", JSON.stringify(data.user));
    setUser(data.user);
    return data.user;
  };

  const loginWithApple = async (idToken, name) => {
    const { data } = await api.post("/auth/apple", { id_token: idToken, name });
    localStorage.setItem("album_token", data.token);
    localStorage.setItem("album_user", JSON.stringify(data.user));
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

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout, loginWithGoogle, loginWithApple, forgotPassword, resetPassword, updateUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);