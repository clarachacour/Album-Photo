import React, { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/lib/auth";
import { TID } from "@/constants/testIds";
import { LogOut, LayoutGrid, User, Package, HelpCircle, Shield, Menu, X } from "lucide-react";
import LanguageSwitcher from "@/components/LanguageSwitcher";

export default function TopNav() {
  const { user, logout } = useAuth();
  const { t } = useTranslation();
  const nav = useNavigate();
  const loc = useLocation();
  const isEditor = loc.pathname.includes("/editor");
  // Phone-sized screens: the links don't fit in the bar, they go in a menu.
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);
  useEffect(() => setMenuOpen(false), [loc.pathname]);
  useEffect(() => {
    if (!menuOpen) return;
    const close = (e) => {
      if (e.type === "keydown" ? e.key === "Escape" : !menuRef.current?.contains(e.target)) setMenuOpen(false);
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", close);
    };
  }, [menuOpen]);
  const logoutAndLeave = () => {
    logout();
    nav("/");
  };
  const mobileLink = "flex items-center gap-3 px-6 py-3 text-sm font-medium text-[color:var(--ink)]/80 hover:bg-[color:var(--paper)] hover:text-[color:var(--ink)]";

  return (
    <header className={`absolute top-0 inset-x-0 z-40 ${isEditor ? "bg-white/80 backdrop-blur-xl border-b border-[color:var(--border-soft)]" : "bg-transparent"}`}>
      <div className="max-w-[1400px] mx-auto px-6 md:px-10 h-16 flex items-center justify-between">
        <Link to="/" data-testid={TID.navBrand} className="group">
          <div className="flex items-baseline gap-2">
            <span className="font-serif-display text-2xl font-medium tracking-tight text-[color:var(--ink)]">Everbook</span>
          </div>
        </Link>
        {user && (
          <nav className="flex items-center gap-2">
            <Link
              to="/dashboard"
              data-testid={TID.navDashboard}
              className="hidden sm:inline-flex items-center gap-2 text-sm font-medium text-[color:var(--ink)]/70 hover:text-[color:var(--ink)] px-3 py-2 transition-colors"
            >
              <LayoutGrid size={14} /> {t("nav.myAlbums")}
            </Link>
            <Link
              to="/orders"
              className="hidden sm:inline-flex items-center gap-2 text-sm font-medium text-[color:var(--ink)]/70 hover:text-[color:var(--ink)] px-3 py-2 transition-colors"
            >
              <Package size={14} /> {t("nav.orders")}
            </Link>
            <Link
              to="/faq"
              className="hidden md:inline-flex items-center gap-2 text-sm font-medium text-[color:var(--ink)]/70 hover:text-[color:var(--ink)] px-3 py-2 transition-colors"
            >
              <HelpCircle size={14} /> {t("nav.faq")}
            </Link>
            {user.is_admin && (
              <Link
                to="/admin/orders"
                className="hidden sm:inline-flex items-center gap-2 text-sm font-medium text-[color:var(--coral)] hover:text-[color:var(--ink)] px-3 py-2 transition-colors"
              >
                <Shield size={14} /> {t("nav.admin")}
              </Link>
            )}
            <Link
              to="/account"
              className="hidden sm:inline-flex items-center gap-2 text-sm font-medium text-[color:var(--ink)]/70 hover:text-[color:var(--ink)] px-3 py-2 transition-colors"
            >
              <User size={14} />
              <span className="hidden md:inline">{user.name}</span>
            </Link>
            <button
              data-testid={TID.navLogout}
              onClick={logoutAndLeave}
              className="hidden sm:inline-flex items-center gap-2 text-sm font-medium text-[color:var(--ink)]/70 hover:text-[color:var(--coral)] px-3 py-2 transition-colors"
            >
              <LogOut size={14} /> {t("nav.logout")}
            </button>
            <LanguageSwitcher className="ml-2 pl-2 border-l border-[color:var(--border-soft)]" />
            <div ref={menuRef} className="sm:hidden">
              <button
                type="button"
                onClick={() => setMenuOpen((o) => !o)}
                aria-expanded={menuOpen}
                aria-label={menuOpen ? t("nav.closeMenu") : t("nav.menu")}
                data-testid="nav-mobile-menu"
                className="inline-flex items-center justify-center w-10 h-10 ml-1 text-[color:var(--ink)]"
              >
                {menuOpen ? <X size={20} /> : <Menu size={20} />}
              </button>
              {menuOpen && (
                <div className="absolute top-16 inset-x-0 bg-white border-y border-[color:var(--border-soft)] shadow-lg py-2" data-testid="nav-mobile-panel">
                  <Link to="/dashboard" className={mobileLink}><LayoutGrid size={16} /> {t("nav.myAlbums")}</Link>
                  <Link to="/orders" className={mobileLink}><Package size={16} /> {t("nav.orders")}</Link>
                  <Link to="/faq" className={mobileLink}><HelpCircle size={16} /> {t("nav.faq")}</Link>
                  {user.is_admin && (
                    <Link to="/admin/orders" className={`${mobileLink} text-[color:var(--coral)]`}><Shield size={16} /> {t("nav.admin")}</Link>
                  )}
                  <Link to="/account" className={mobileLink}><User size={16} /> {t("nav.account")}</Link>
                  <button type="button" onClick={logoutAndLeave} className={`${mobileLink} w-full text-left border-t border-[color:var(--border-soft)] mt-2 pt-4`}>
                    <LogOut size={16} /> {t("nav.logout")}
                  </button>
                </div>
              )}
            </div>
          </nav>
        )}
        {!user && (
          <nav className="flex items-center gap-4">
            <Link to="/auth" className="text-sm font-medium text-[color:var(--ink)]/70 hover:text-[color:var(--ink)] transition-colors">
              {t("nav.signIn")}
            </Link>
            <LanguageSwitcher />
          </nav>
        )}
      </div>
    </header>
  );
}
