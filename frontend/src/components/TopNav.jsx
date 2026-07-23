import React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { TID } from "@/constants/testIds";
import { LogOut, LayoutGrid } from "lucide-react";

export default function TopNav() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const isEditor = loc.pathname.includes("/editor");

  return (
    <header className={`fixed top-0 inset-x-0 z-40 ${isEditor ? "bg-white/80 backdrop-blur-xl border-b border-[color:var(--border-soft)]" : "bg-transparent"}`}>
      <div className="max-w-[1400px] mx-auto px-6 md:px-10 h-16 flex items-center justify-between">
        <Link to={user ? "/dashboard" : "/"} data-testid={TID.navBrand} className="group">
          <div className="flex items-baseline gap-2">
            <span className="font-serif-display text-2xl font-medium tracking-tight text-[color:var(--ink)]">Fable</span>
            <span className="eyebrow text-[color:var(--coral)]">studio</span>
          </div>
        </Link>
        {user && (
          <nav className="flex items-center gap-2">
            <Link
              to="/dashboard"
              data-testid={TID.navDashboard}
              className="hidden sm:inline-flex items-center gap-2 text-sm font-medium text-[color:var(--ink)]/70 hover:text-[color:var(--ink)] px-3 py-2 transition-colors"
            >
              <LayoutGrid size={14} /> Mes albums
            </Link>
            <span className="hidden md:inline-block eyebrow">{user.name}</span>
            <button
              data-testid={TID.navLogout}
              onClick={() => {
                logout();
                nav("/");
              }}
              className="inline-flex items-center gap-2 text-sm font-medium text-[color:var(--ink)]/70 hover:text-[color:var(--coral)] px-3 py-2 transition-colors"
            >
              <LogOut size={14} /> Sortir
            </button>
          </nav>
        )}
        {!user && (
          <nav className="flex items-center gap-4">
            <Link to="/auth" className="text-sm font-medium text-[color:var(--ink)]/70 hover:text-[color:var(--ink)] transition-colors">
              Se connecter
            </Link>
          </nav>
        )}
      </div>
    </header>
  );
}
