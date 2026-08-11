import React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { TID } from "@/constants/testIds";
import { LogOut, LayoutGrid, User, Package, HelpCircle } from "lucide-react";

export default function TopNav() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const isEditor = loc.pathname.includes("/editor");

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
              <LayoutGrid size={14} /> My albums
            </Link>
            <Link
              to="/orders"
              className="hidden sm:inline-flex items-center gap-2 text-sm font-medium text-[color:var(--ink)]/70 hover:text-[color:var(--ink)] px-3 py-2 transition-colors"
            >
              <Package size={14} /> Orders
            </Link>
            <Link
              to="/faq"
              className="hidden md:inline-flex items-center gap-2 text-sm font-medium text-[color:var(--ink)]/70 hover:text-[color:var(--ink)] px-3 py-2 transition-colors"
            >
              <HelpCircle size={14} /> FAQ
            </Link>
            <Link
              to="/account"
              className="inline-flex items-center gap-2 text-sm font-medium text-[color:var(--ink)]/70 hover:text-[color:var(--ink)] px-3 py-2 transition-colors"
            >
              <User size={14} />
              <span className="hidden md:inline">{user.name}</span>
            </Link>
            <button
              data-testid={TID.navLogout}
              onClick={() => {
                logout();
                nav("/");
              }}
              className="inline-flex items-center gap-2 text-sm font-medium text-[color:var(--ink)]/70 hover:text-[color:var(--coral)] px-3 py-2 transition-colors"
            >
              <LogOut size={14} /> Logout
            </button>
          </nav>
        )}
        {!user && (
          <nav className="flex items-center gap-4">
            <Link to="/auth" className="text-sm font-medium text-[color:var(--ink)]/70 hover:text-[color:var(--ink)] transition-colors">
              Sign in
            </Link>
          </nav>
        )}
      </div>
    </header>
  );
}