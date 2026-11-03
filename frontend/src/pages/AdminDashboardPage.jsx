import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowDownRight, ArrowLeft, ArrowUpRight, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { findTemplate } from "@/lib/coverThemes";
import { parseDate } from "@/lib/dates";

/**
 * The admin's dashboard (backend routers/stats.py): key figures against the
 * period before, what needs attention, the customers' journey, week by
 * week, then albums, orders, accounts and contact messages. The admin's own
 * account and orders are left out.
 */
const PERIODS = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 365, label: "12 months" },
  { days: 0, label: "Since the start" },
];

const STEPS = { accounts: "Accounts created", album: "Started an album", photos: "Added photos", cart: "Put in the cart", ordered: "Ordered" };
const STATUSES = {
  pending_payment: "Placed (cash on delivery)", paid: "Paid", processing: "Preparing", printing: "Printing",
  ready_for_delivery: "Ready for pickup", shipped: "On its way", delivered: "Delivered", available: "Available (PDF)", cancelled: "Cancelled",
};
const WORDS = { en: "English", fr: "French", email: "Email + password", google: "Google", apple: "Apple", print: "Printed", digital: "PDF", unknown: "Not known" };

const usd = (cents) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format((cents || 0) / 100);
const pct = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0);
const day = (iso) => {
  const d = parseDate(iso);
  return d ? d.toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "";
};
const shortWeek = (start) => `${Number(start.slice(8, 10))}/${Number(start.slice(5, 7))}`;
const week = (start) => new Date(`${start}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });

function Card({ title, children, className = "" }) {
  return (
    <section className={`border border-[color:var(--border-soft)] bg-white/40 p-4 ${className}`}>
      {title && <h2 className="text-xs uppercase tracking-widest text-[color:var(--muted)] mb-3">{title}</h2>}
      {children}
    </section>
  );
}

function Change({ value, previous, money }) {
  if (previous === null || previous === undefined) return null;
  const diff = value - previous;
  const was = money ? usd(previous) : previous;
  if (!diff) return <p className="text-xs text-[color:var(--muted)]">Same as the period before</p>;
  const up = diff > 0;
  const Arrow = up ? ArrowUpRight : ArrowDownRight;
  return (
    <p className={`text-xs inline-flex items-center gap-0.5 ${up ? "text-emerald-700" : "text-red-700"}`}>
      <Arrow size={12} /> {previous ? `${up ? "+" : ""}${Math.round((diff / previous) * 100)}%` : "new"}
      <span className="text-[color:var(--muted)] ml-1">vs {was} before</span>
    </p>
  );
}

function Kpi({ label, figure, money, suffix = "" }) {
  return (
    <div className="border border-[color:var(--border-soft)] bg-white/40 px-3 py-3">
      <p className="text-xs text-[color:var(--muted)]">{label}</p>
      <p className="text-2xl font-semibold tabular-nums">{money ? usd(figure.value) : `${figure.value}${suffix}`}</p>
      <Change value={figure.value} previous={figure.previous} money={money} />
    </div>
  );
}

function Bars({ rows, label = (k) => WORDS[k] || k, empty = "Nothing yet." }) {
  if (!rows?.length) return <p className="text-sm text-[color:var(--muted)]">{empty}</p>;
  const total = rows.reduce((s, r) => s + r.count, 0);
  const top = Math.max(...rows.map((r) => r.count));
  return (
    <ul className="space-y-1.5">
      {rows.map((r) => (
        <li key={r.key}>
          <div className="flex justify-between gap-3 text-sm">
            <span className="truncate">{label(r.key)}</span>
            <span className="tabular-nums shrink-0"><strong>{r.count}</strong> <span className="text-[color:var(--muted)]">· {pct(r.count, total)}%</span></span>
          </div>
          <div className="h-1.5 bg-[color:var(--border-soft)]">
            <div className="h-1.5 bg-[color:var(--coral)]" style={{ width: `${pct(r.count, top)}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function Figure({ label, value, hint }) {
  return (
    <div>
      <p className="text-xs text-[color:var(--muted)]">{label}</p>
      <p className="text-lg font-semibold tabular-nums">{value ?? "—"}</p>
      {hint && <p className="text-xs text-[color:var(--muted)]">{hint}</p>}
    </div>
  );
}

function WeekChart({ weekly, field, label, money }) {
  const top = Math.max(1, ...weekly.map((w) => w[field]));
  return (
    <div>
      <p className="text-sm mb-2">{label}</p>
      <div className="flex items-end gap-1 h-28" role="img" aria-label={`${label}, week by week`}>
        {weekly.map((w) => (
          <div key={w.week} className="flex-1 flex flex-col items-center justify-end h-full" title={`Week of ${week(w.week)}: ${money ? usd(w[field]) : w[field]}`}>
            <span className="text-[10px] tabular-nums text-[color:var(--muted)]">{w[field] ? (money ? usd(w[field]) : w[field]) : ""}</span>
            <div className="w-full bg-[color:var(--coral)]" style={{ height: `${(w[field] / top) * 80}%`, minHeight: w[field] ? 2 : 0 }} />
          </div>
        ))}
      </div>
      <div className="flex gap-1 mt-1">
        {weekly.map((w, i) => (
          <span key={w.week} className="flex-1 text-center text-[10px] text-[color:var(--muted)] whitespace-nowrap">{i % 2 === weekly.length % 2 ? "" : shortWeek(w.week)}</span>
        ))}
      </div>
    </div>
  );
}

export default function AdminDashboardPage() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [state, setState] = useState("loading");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    setState("loading");
    api
      .get("/admin/dashboard", { params: { days } })
      .then(({ data: d }) => {
        setData(d);
        setState("ready");
      })
      .catch((err) => setState(err?.response?.status === 403 ? "forbidden" : "failed"));
  }, [days, reload]);

  if (state === "forbidden") {
    return (
      <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
        <div className="max-w-[600px] mx-auto text-center">
          <h1 className="font-serif-display text-3xl tracking-tight mb-3">Not available</h1>
          <p className="text-ink/70">This page is only visible to the account running the business.</p>
        </div>
      </main>
    );
  }

  const k = data?.kpis;
  const funnel = data?.funnel || [];
  const accounts = funnel[0]?.count || 0;
  const periodLabel = PERIODS.find((p) => p.days === days)?.label.toLowerCase();

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-4 md:px-12" data-testid="admin-dashboard">
      <div className="max-w-[1400px] mx-auto">
        <Link to="/admin/orders" className="inline-flex items-center gap-1 text-xs text-[color:var(--muted)] hover:text-[color:var(--ink)] mb-3">
          <ArrowLeft size={13} /> All orders
        </Link>
        <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
          <div>
            <h1 className="font-serif-display text-4xl tracking-tight">Dashboard</h1>
            {data && <p className="text-xs text-[color:var(--muted)] mt-1">Updated {parseDate(data.generated_at)?.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}. Your own account and tests are not counted.</p>}
          </div>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Period">
            {PERIODS.map((p) => (
              <button key={p.days} type="button" onClick={() => setDays(p.days)} aria-pressed={days === p.days}
                className={`text-xs border px-3 py-1.5 ${days === p.days ? "border-[color:var(--ink)] bg-[color:var(--ink)] text-[color:var(--paper)]" : "border-ink/20 hover:border-[color:var(--ink)]"}`}>
                {p.label}
              </button>
            ))}
            <button type="button" onClick={() => setReload((n) => n + 1)} className="text-xs border border-ink/20 px-2 py-1.5 hover:border-[color:var(--ink)]" aria-label="Refresh">
              <RefreshCw size={13} />
            </button>
          </div>
        </div>

        {state === "failed" && <p className="text-sm text-[color:var(--muted)]">Couldn't load the dashboard. Try again in a moment.</p>}
        {state === "loading" && !data && <p className="text-sm text-[color:var(--muted)]">Loading…</p>}

        {data && (
          <div className={`space-y-6 ${state === "loading" ? "opacity-50" : ""}`}>
            {/* Key figures */}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2" data-testid="dashboard-kpis">
              <Kpi label="Orders" figure={k.orders} />
              <Kpi label="Revenue (incl. delivery)" figure={k.revenue_cents} money />
              <Kpi label="Average order" figure={k.average_order_cents} money />
              <Kpi label="Books to print" figure={k.books} />
              <Kpi label="New accounts" figure={k.accounts} />
              <Kpi label="Albums started" figure={k.albums_started} />
              <Kpi label="New accounts who ordered" figure={k.conversion_percent} suffix="%" />
              <Kpi label="Contact messages" figure={k.messages} />
            </div>

            {/* Needs attention */}
            <Card title="Right now">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <Figure label="Orders in production" value={data.now.orders_in_production} />
                <Figure label="Orders on their way" value={data.now.orders_on_their_way} />
                <Figure label="Carts waiting" value={data.now.carts_waiting} hint="a reminder is emailed after a day" />
                <Figure label="Albums in progress" value={data.now.albums_in_progress} hint={`${data.albums.in_progress_older_than_7_days} started over a week ago`} />
              </div>
              {data.orders.pdf_not_ready.count > 0 ? (
                <div className="border border-amber-300 bg-amber-50 p-3" data-testid="dashboard-pdf-not-ready">
                  <p className="text-sm font-semibold inline-flex items-center gap-1.5"><AlertTriangle size={14} /> {data.orders.pdf_not_ready.count} printed {data.orders.pdf_not_ready.count === 1 ? "order has" : "orders have"} no PDF yet</p>
                  <ul className="text-sm mt-1.5 space-y-0.5">
                    {data.orders.pdf_not_ready.orders.map((o) => (
                      <li key={o.number} className="tabular-nums">
                        <span className="font-mono">{o.number}</span> · ordered {day(o.created_at)} · {STATUSES[o.status] || o.status}
                        {o.failed && <span className="text-red-700"> · generation failed: regenerate it in All orders</span>}
                      </li>
                    ))}
                  </ul>
                  <p className="text-xs text-[color:var(--muted)] mt-1.5">A PDF usually takes a few minutes. One still missing after an hour needs a look.</p>
                </div>
              ) : (
                <p className="text-sm text-emerald-700">Every printed order has its PDF.</p>
              )}
            </Card>

            <div className="grid lg:grid-cols-2 gap-6">
              {/* Journey */}
              <Card title={`Journey of the accounts created in the last ${periodLabel}`}>
                <ol className="space-y-2" data-testid="dashboard-funnel">
                  {funnel.map((f, i) => {
                    const previous = i ? funnel[i - 1].count : null;
                    return (
                      <li key={f.step}>
                        <div className="flex items-baseline justify-between text-sm gap-3">
                          <span>{STEPS[f.step] || f.step}</span>
                          <span className="tabular-nums"><strong>{f.count}</strong>{i > 0 && <span className="text-[color:var(--muted)]"> · {pct(f.count, accounts)}%</span>}</span>
                        </div>
                        <div className="h-2 bg-[color:var(--border-soft)] mt-1">
                          <div className="h-2 bg-[color:var(--coral)]" style={{ width: `${pct(f.count, accounts)}%` }} />
                        </div>
                        {i > 0 && previous > f.count && (
                          <p className="text-xs text-[color:var(--muted)] mt-0.5">{previous - f.count} stopped here ({100 - pct(f.count, previous)}% of the step before)</p>
                        )}
                      </li>
                    );
                  })}
                </ol>
              </Card>

              {/* Week by week */}
              <Card title="The last 12 weeks">
                <div className="grid sm:grid-cols-2 gap-6">
                  <WeekChart weekly={data.weekly} field="orders" label="Orders" />
                  <WeekChart weekly={data.weekly} field="revenue_cents" label="Revenue" money />
                  <WeekChart weekly={data.weekly} field="accounts" label="New accounts" />
                  <WeekChart weekly={data.weekly} field="albums" label="Albums started" />
                </div>
              </Card>
            </div>

            {/* Albums */}
            <h2 className="font-serif-display text-2xl tracking-tight pt-2">Albums</h2>
            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
              <Card title="Templates chosen (albums started)">
                <Bars rows={data.albums.started_by.templates} label={(key) => findTemplate(key)?.name || key} />
              </Card>
              <Card title="Templates of the albums ordered">
                <Bars rows={data.albums.ordered_by.templates} label={(key) => findTemplate(key)?.name || key} empty="No order in this period." />
              </Card>
              <Card title="Pages chosen (albums started)">
                <Bars rows={data.albums.started_by.pages} label={(key) => `${key} pages`} />
                <h3 className="text-xs uppercase tracking-widest text-[color:var(--muted)] mt-4 mb-2">Pages of the albums ordered</h3>
                <Bars rows={data.albums.ordered_by.pages} label={(key) => `${key} pages`} empty="No order in this period." />
              </Card>
              <Card title="Format (albums started)">
                <Bars rows={data.albums.started_by.sizes} />
                <div className="mt-4"><Bars rows={data.albums.started_by.orientations} label={(key) => key.charAt(0).toUpperCase() + key.slice(1)} /></div>
              </Card>
            </div>
            <Card title="Photos">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Figure label="Photos per ordered album (average)" value={data.albums.photos_per_ordered_album.average} hint={data.albums.photos_per_ordered_album.median !== null ? `median ${data.albums.photos_per_ordered_album.median}` : "no order in this period"} />
                <Figure label="Photos per album in progress (average)" value={data.albums.photos_per_album_in_progress.average} hint={data.albums.photos_per_album_in_progress.median !== null ? `median ${data.albums.photos_per_album_in_progress.median}` : null} />
                <Figure label="Albums in progress, not ordered" value={data.albums.in_progress} />
                <Figure label="…of which without any photo" value={data.albums.in_progress_without_photos} hint="started, then left" />
              </div>
            </Card>

            {/* Orders */}
            <h2 className="font-serif-display text-2xl tracking-tight pt-2">Orders</h2>
            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
              <Card title="Where the period's orders are">
                <Bars rows={data.orders.by_status} label={(key) => STATUSES[key] || key} empty="No order in this period." />
              </Card>
              <Card title="Books by size">
                <Bars rows={data.orders.books_by_size} empty="No order in this period." />
                <h3 className="text-xs uppercase tracking-widest text-[color:var(--muted)] mt-4 mb-2">Printed or PDF</h3>
                <Bars rows={data.orders.by_kind} empty="No order in this period." />
              </Card>
              <Card title="Delivery areas">
                <Bars rows={data.orders.areas} empty="No order in this period." />
              </Card>
              <Card title="Customers">
                <div className="space-y-3">
                  <Figure label="Delivered, days from order (average)" value={data.orders.delivery_days.average} hint={data.orders.delivery_days.orders ? `median ${data.orders.delivery_days.median} · ${data.orders.delivery_days.orders} delivered` : "nothing delivered in this period"} />
                  <Figure label="Customers (all time)" value={data.orders.customers} />
                  <Figure label="Ordered again" value={data.orders.repeat_customers} hint={data.orders.customers ? `${pct(data.orders.repeat_customers, data.orders.customers)}% of customers` : null} />
                </div>
              </Card>
            </div>
            <Card title="Promo codes used in the period">
              {data.orders.promo_codes.length ? (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-widest text-[color:var(--muted)] border-b border-[color:var(--border-soft)]">
                      <th className="py-2 pr-3">Code</th><th className="py-2 pr-3 text-right">Orders</th><th className="py-2 text-right">Discount given</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.orders.promo_codes.map((p) => (
                      <tr key={p.code} className="border-b border-[color:var(--border-soft)] last:border-0 tabular-nums">
                        <td className="py-1.5 pr-3 font-mono">{p.code}</td><td className="py-1.5 pr-3 text-right">{p.orders}</td><td className="py-1.5 text-right">{usd(p.discount_cents)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="text-sm text-[color:var(--muted)]">No promo code used in this period.</p>
              )}
            </Card>

            {/* Accounts and messages */}
            <h2 className="font-serif-display text-2xl tracking-tight pt-2">Accounts and messages</h2>
            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
              <Card title="Accounts (all time)">
                <div className="space-y-3">
                  <Figure label="Accounts" value={data.users.total} hint={`${data.users.new} new in the last ${periodLabel}`} />
                  <Figure label="Email confirmed" value={data.users.verified} hint={`${pct(data.users.verified, data.users.total)}% of accounts`} />
                  <Figure label="With at least one order" value={data.users.with_an_order} hint={`${pct(data.users.with_an_order, data.users.total)}% of accounts`} />
                </div>
              </Card>
              <Card title="Language">
                <Bars rows={data.users.languages} />
              </Card>
              <Card title="Sign-in">
                <Bars rows={data.users.sign_in} />
              </Card>
              <Card title="Contact messages">
                <Figure label={`In the last ${periodLabel}`} value={data.messages.period} hint={`${data.messages.total} in all`} />
                {data.messages.latest.length > 0 && (
                  <ul className="text-sm mt-3 space-y-1">
                    {data.messages.latest.map((m, i) => (
                      <li key={i} className="flex justify-between gap-2"><span className="truncate">{m.subject}</span><span className="text-[color:var(--muted)] shrink-0">{day(m.created_at)}</span></li>
                    ))}
                  </ul>
                )}
              </Card>
            </div>

            {/* Week by week, in figures */}
            <Card title="Week by week">
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="dashboard-weekly">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-widest text-[color:var(--muted)] border-b border-[color:var(--border-soft)]">
                      <th className="py-2 pr-3 whitespace-nowrap">Week of</th>
                      <th className="py-2 pr-3 text-right">Accounts</th>
                      <th className="py-2 pr-3 text-right">Albums</th>
                      <th className="py-2 pr-3 text-right">Orders</th>
                      <th className="py-2 pr-3 text-right">Revenue</th>
                      <th className="py-2 text-right">Messages</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...data.weekly].reverse().map((w) => (
                      <tr key={w.week} className="border-b border-[color:var(--border-soft)] last:border-0 tabular-nums">
                        <td className="py-1.5 pr-3 whitespace-nowrap">{week(w.week)}</td>
                        <td className="py-1.5 pr-3 text-right">{w.accounts}</td>
                        <td className="py-1.5 pr-3 text-right">{w.albums}</td>
                        <td className="py-1.5 pr-3 text-right">{w.orders}</td>
                        <td className="py-1.5 pr-3 text-right">{usd(w.revenue_cents)}</td>
                        <td className="py-1.5 text-right">{w.messages}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-[color:var(--muted)] mt-3">Cancelled orders are left out of orders and revenue. Albums deleted later still count in albums started.</p>
            </Card>
          </div>
        )}
      </div>
    </main>
  );
}
