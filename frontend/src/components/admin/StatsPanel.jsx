import React, { useEffect, useState } from "react";
import { BarChart3, ChevronDown } from "lucide-react";
import { api } from "@/lib/api";

/**
 * Statistics, in the admin (backend routers/stats.py): the journey of the
 * accounts created in the period, what was ordered in it, and the last 12
 * weeks. The admin's own account and orders are left out.
 */
const PERIODS = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 0, label: "Since the start" },
];

const STEPS = {
  accounts: "Accounts created",
  album: "Started an album",
  photos: "Added photos",
  cart: "Put in the cart",
  ordered: "Ordered",
};

const usd = (cents) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format((cents || 0) / 100);
const pct = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0);

function Figure({ label, value, hint }) {
  return (
    <div className="border border-[color:var(--border-soft)] px-3 py-2.5">
      <p className="text-xs text-[color:var(--muted)]">{label}</p>
      <p className="text-xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="text-xs text-[color:var(--muted)]">{hint}</p>}
    </div>
  );
}

export default function StatsPanel() {
  const [open, setOpen] = useState(false);
  const [days, setDays] = useState(30);
  const [stats, setStats] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open) return;
    setStats(null);
    setFailed(false);
    api.get("/admin/stats", { params: { days } }).then(({ data }) => setStats(data)).catch(() => setFailed(true));
  }, [open, days]);

  const funnel = stats?.funnel || [];
  const accounts = funnel[0]?.count || 0;
  const period = stats?.period;

  return (
    <section className="mb-8 border border-[color:var(--border-soft)]" data-testid="admin-stats">
      <button type="button" onClick={() => setOpen((o) => !o)} className="w-full flex items-center justify-between px-4 py-3 text-left">
        <span className="inline-flex items-center gap-2 text-sm font-semibold"><BarChart3 size={14} /> Statistics</span>
        <ChevronDown size={16} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="px-4 pb-4 border-t border-[color:var(--border-soft)]">
          <div className="flex flex-wrap gap-2 py-4" role="group" aria-label="Period">
            {PERIODS.map((p) => (
              <button
                key={p.days}
                type="button"
                onClick={() => setDays(p.days)}
                aria-pressed={days === p.days}
                className={`text-xs border px-3 py-1.5 ${days === p.days ? "border-[color:var(--ink)] bg-[color:var(--ink)] text-[color:var(--paper)]" : "border-ink/20"}`}
              >
                {p.label}
              </button>
            ))}
          </div>

          {failed ? (
            <p className="text-sm text-[color:var(--muted)]">Couldn't load the statistics.</p>
          ) : !stats ? (
            <p className="text-sm text-[color:var(--muted)]">Loading…</p>
          ) : (
            <>
              <h3 className="text-xs uppercase tracking-widest text-[color:var(--muted)] mb-2">Journey of the accounts created in the period</h3>
              <ol className="space-y-2 mb-6" data-testid="stats-funnel">
                {funnel.map((f, i) => {
                  const previous = i ? funnel[i - 1].count : null;
                  return (
                    <li key={f.step}>
                      <div className="flex items-baseline justify-between text-sm gap-3">
                        <span>{STEPS[f.step] || f.step}</span>
                        <span className="tabular-nums">
                          <strong>{f.count}</strong>
                          {i > 0 && <span className="text-[color:var(--muted)]"> · {pct(f.count, accounts)}% of accounts</span>}
                        </span>
                      </div>
                      <div className="h-2 bg-[color:var(--border-soft)] mt-1">
                        <div className="h-2 bg-[color:var(--coral)]" style={{ width: `${accounts ? pct(f.count, accounts) : 0}%` }} />
                      </div>
                      {i > 0 && previous > 0 && previous > f.count && (
                        <p className="text-xs text-[color:var(--muted)] mt-0.5">{previous - f.count} stopped here ({100 - pct(f.count, previous)}% of the step before)</p>
                      )}
                    </li>
                  );
                })}
              </ol>

              <h3 className="text-xs uppercase tracking-widest text-[color:var(--muted)] mb-2">In the period</h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-2" data-testid="stats-period">
                <Figure label="Orders" value={period.orders} hint={`${period.customers} ${period.customers === 1 ? "customer" : "customers"}`} />
                <Figure label="Books to print" value={period.books} />
                <Figure label="Revenue (incl. delivery)" value={usd(period.revenue_cents)} />
                <Figure label="Average order" value={usd(period.average_order_cents)} />
                <Figure label="Albums started" value={period.albums_started} />
                <Figure label="Orders with a promo code" value={period.with_promo} />
                <Figure label="Cancelled orders" value={period.cancelled} />
              </div>
              <p className="text-xs text-[color:var(--muted)] mb-6">
                Right now: {stats.now.carts_waiting} {stats.now.carts_waiting === 1 ? "cart" : "carts"} waiting, {stats.now.albums_in_progress} {stats.now.albums_in_progress === 1 ? "album" : "albums"} in progress (not ordered).
              </p>

              <h3 className="text-xs uppercase tracking-widest text-[color:var(--muted)] mb-2">Week by week</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="stats-weekly">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-widest text-[color:var(--muted)] border-b border-[color:var(--border-soft)]">
                      <th className="py-2 pr-3 whitespace-nowrap">Week of</th>
                      <th className="py-2 pr-3 text-right">Accounts</th>
                      <th className="py-2 pr-3 text-right">Albums</th>
                      <th className="py-2 pr-3 text-right">Orders</th>
                      <th className="py-2 text-right">Revenue</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...stats.weekly].reverse().map((w) => (
                      <tr key={w.week} className="border-b border-[color:var(--border-soft)] last:border-0 tabular-nums">
                        <td className="py-1.5 pr-3 whitespace-nowrap">{new Date(`${w.week}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" })}</td>
                        <td className="py-1.5 pr-3 text-right">{w.accounts}</td>
                        <td className="py-1.5 pr-3 text-right">{w.albums}</td>
                        <td className="py-1.5 pr-3 text-right">{w.orders}</td>
                        <td className="py-1.5 text-right">{usd(w.revenue_cents)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-[color:var(--muted)] mt-3">Your own account and test orders are not counted. Cancelled orders are left out of orders and revenue.</p>
            </>
          )}
        </div>
      )}
    </section>
  );
}
