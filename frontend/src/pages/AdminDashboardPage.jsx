import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowDownRight, ArrowLeft, ArrowUpRight, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { findTemplate } from "@/lib/coverThemes";
import { parseDate } from "@/lib/dates";

/**
 * The admin's dashboard (backend routers/stats.py): key figures against the
 * period just before, the money, what needs attention, the customers'
 * journey, over time, then albums and orders. An order is a checkout (one
 * cart, one or more albums). The admin's own account and orders are left out.
 */
const PERIODS = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 365, label: "12 months" },
  { days: 0, label: "Since the start" },
];
const RANGES = [
  { key: "month", label: "Last month", source: "weekly", count: 5 },
  { key: "3m", label: "3 months", source: "monthly", count: 3 },
  { key: "6m", label: "6 months", source: "monthly", count: 6 },
  { key: "12m", label: "12 months", source: "monthly", count: 12 },
];

const STEPS = { accounts: "Accounts created", album: "Created an album", photos: "Added photos", cart: "Put in the cart", ordered: "Ordered" };
const STATUSES = {
  pending_payment: "Placed (cash on delivery)", paid: "Paid", processing: "Preparing", printing: "Printing",
  ready_for_delivery: "Ready for pickup", shipped: "On its way", delivered: "Delivered", available: "Available (PDF)", cancelled: "Cancelled",
};

const usd = (cents) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format((cents || 0) / 100);
const pct = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0);
const day = (iso) => parseDate(iso)?.toLocaleDateString("en-GB", { day: "numeric", month: "short" }) || "";
const utc = (start) => new Date(`${start}T00:00:00Z`);
const bucketLabel = (start, source) =>
  source === "weekly"
    ? `${Number(start.slice(8, 10))}/${Number(start.slice(5, 7))}`
    : utc(start).toLocaleDateString("en-GB", { month: "short", timeZone: "UTC" });
const bucketName = (start, source) =>
  source === "weekly"
    ? `Week of ${utc(start).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" })}`
    : utc(start).toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });
const isCurrent = (d) => Boolean(d?.kpis && d.money && d.weekly && d.monthly && d.albums?.templates && d.orders?.printed && d.gift_cards && d.now);
const capital = (s) => s.charAt(0).toUpperCase() + s.slice(1);

function Card({ title, children, className = "" }) {
  return (
    <section className={`min-w-0 border border-[color:var(--border-soft)] bg-white/40 p-4 ${className}`}>
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
      <Arrow size={12} /> {previous > 0 ? `${up ? "+" : ""}${Math.round((diff / previous) * 100)}%` : up ? "up" : "down"}
      <span className="text-[color:var(--muted)] ml-1">vs {was} before</span>
    </p>
  );
}

function Kpi({ label, figure, money, hint }) {
  return (
    <div className="border border-[color:var(--border-soft)] bg-white/40 px-3 py-3">
      <p className="text-xs text-[color:var(--muted)]">{label}</p>
      <p className="text-2xl font-semibold tabular-nums">{money ? usd(figure.value) : figure.value}</p>
      {hint && <p className="text-xs text-[color:var(--muted)]">{hint}</p>}
      <Change value={figure.value} previous={figure.previous} money={money} />
    </div>
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

function Bars({ rows, label = (k) => k, empty = "Nothing in this period." }) {
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

/** Created and ordered side by side, for one choice (template, pages…). */
function Choices({ rows, label, name }) {
  if (!rows?.length) return <p className="text-sm text-[color:var(--muted)]">Nothing in this period.</p>;
  const top = Math.max(1, ...rows.map((r) => Math.max(r.created, r.ordered)));
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs uppercase tracking-widest text-[color:var(--muted)] border-b border-[color:var(--border-soft)]">
          <th className="py-2 pr-3">{name}</th>
          <th className="py-2 pr-3 text-right">Created</th>
          <th className="py-2 text-right">Ordered</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.key} className="border-b border-[color:var(--border-soft)] last:border-0 align-top">
            <td className="py-1.5 pr-3">
              <span>{label(r.key)}</span>
              <div className="flex flex-col gap-0.5 mt-1" aria-hidden="true">
                <div className="h-1 bg-ink/25" style={{ width: `${(r.created / top) * 100}%` }} />
                <div className="h-1 bg-[color:var(--coral)]" style={{ width: `${(r.ordered / top) * 100}%` }} />
              </div>
            </td>
            <td className="py-1.5 pr-3 text-right tabular-nums">{r.created}</td>
            <td className="py-1.5 text-right tabular-nums">{r.ordered}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function OverTimeChart({ rows, field, label, money, source }) {
  const top = Math.max(1, ...rows.map((r) => Math.abs(r[field])));
  return (
    <div>
      <p className="text-sm mb-2">{label}</p>
      <div className="flex items-end gap-1.5 h-28" role="img" aria-label={`${label}, ${source === "weekly" ? "week by week" : "month by month"}`}>
        {rows.map((r) => (
          <div key={r.start} className="flex-1 flex flex-col items-center justify-end h-full" title={`${bucketName(r.start, source)}: ${money ? usd(r[field]) : r[field]}`}>
            <span className="text-[10px] tabular-nums text-[color:var(--muted)] whitespace-nowrap">{r[field] ? (money ? usd(r[field]) : r[field]) : ""}</span>
            <div className={`w-full ${r[field] < 0 ? "bg-red-400" : "bg-[color:var(--coral)]"}`} style={{ height: `${(Math.abs(r[field]) / top) * 78}%`, minHeight: r[field] ? 2 : 0 }} />
          </div>
        ))}
      </div>
      <div className="flex gap-1.5 mt-1">
        {rows.map((r) => (
          <span key={r.start} className="flex-1 text-center text-[10px] text-[color:var(--muted)] whitespace-nowrap">{bucketLabel(r.start, source)}</span>
        ))}
      </div>
    </div>
  );
}

export default function AdminDashboardPage() {
  const [days, setDays] = useState(30);
  const [range, setRange] = useState("3m");
  const [data, setData] = useState(null);
  const [state, setState] = useState("loading");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    setState("loading");
    api
      .get("/admin/dashboard", { params: { days } })
      .then(({ data: d }) => {
        // A server still on an older version answers without some parts
        // (the site is updated first): said, rather than a broken page.
        if (!isCurrent(d)) {
          setState("outdated");
          return;
        }
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
  const chosen = RANGES.find((r) => r.key === range);
  const overTime = data ? (data[chosen.source] || []).slice(-chosen.count) : [];
  const money = data?.money;
  const templateName = (key) => findTemplate(key)?.name || (key === "unknown" ? "Not known" : key);

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-4 md:px-12" data-testid="admin-dashboard">
      <div className="max-w-[1400px] mx-auto">
        <Link to="/admin/orders" className="inline-flex items-center gap-1 text-xs text-[color:var(--muted)] hover:text-[color:var(--ink)] mb-3">
          <ArrowLeft size={13} /> All orders
        </Link>
        <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
          <div>
            <h1 className="font-serif-display text-4xl tracking-tight">Dashboard</h1>
            {data && (
              <p className="text-xs text-[color:var(--muted)] mt-1">
                Updated {parseDate(data.generated_at)?.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}. Your own account and tests are not counted.
              </p>
            )}
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
        {state === "outdated" && (
          <p className="text-sm text-[color:var(--muted)]" data-testid="dashboard-outdated">
            The server is still being updated to this version of the dashboard. Refresh in a few minutes.
          </p>
        )}
        {state === "loading" && !data && <p className="text-sm text-[color:var(--muted)]">Loading…</p>}

        {data && state !== "outdated" && (
          <div className={`space-y-6 ${state === "loading" ? "opacity-50" : ""}`}>
            {/* Key figures */}
            <div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2" data-testid="dashboard-kpis">
                <Kpi label="Orders" figure={k.orders} hint="one cart = one order" />
                <Kpi label="Albums ordered" figure={k.albums_ordered} hint="every album in those orders" />
                <Kpi label="Revenue (paid by customers)" figure={k.revenue_cents} money />
                <Kpi label="Margin (after printing and delivery)" figure={k.margin_cents} money />
                <Kpi label="Average order" figure={k.average_order_cents} money />
                <Kpi label="New accounts" figure={k.accounts} />
                <Kpi label="Albums created" figure={k.albums_started} hint="ordered or not" />
                <Kpi label="Contact messages" figure={k.messages} />
              </div>
              {days > 0 && <p className="text-xs text-[color:var(--muted)] mt-2">Each figure is compared with the {days} days just before (the period before).</p>}
            </div>

            {/* Money */}
            <Card title={`Money, last ${periodLabel}`}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="dashboard-money">
                <Figure
                  label="Paid by customers"
                  value={usd(money.revenue_cents)}
                  hint={`orders ${usd(money.orders_cents)} (after promo codes) + gift cards ${usd(money.gift_cards_cents)}`}
                />
                <Figure label="− Printing (Bookstop)" value={usd(money.printing_cents)} hint="the printer's price list + envelopes" />
                <Figure label="− Delivery (Wakilni)" value={usd(money.delivery_cents)} hint="$5 per delivery" />
                <Figure label="= Margin" value={usd(money.margin_cents)} hint={money.revenue_cents ? `${pct(money.margin_cents, money.revenue_cents)}% of what customers paid` : null} />
              </div>
              {money.printing_unknown > 0 && (
                <p className="text-xs text-amber-700 mt-3">{money.printing_unknown} album(s) past 100 pages in a format the price list doesn't cover: their printing isn't counted.</p>
              )}
              <p className="text-xs text-[color:var(--muted)] mt-3">
                Orders placed and gift cards bought in the period, cancelled orders left out. An order paid with a gift card only counts what was paid on top, so nothing is counted twice. Cash on delivery: the money comes in when the book is delivered.
              </p>
            </Card>

            {/* Needs attention */}
            <Card title="Right now">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <Figure label="Orders in production" value={data.now.orders_in_production} />
                <Figure label="Orders on their way" value={data.now.orders_on_their_way} />
                <Figure label="Carts waiting" value={data.now.carts_waiting} hint="a reminder is emailed after a day" />
                <Figure label="Albums in progress (not ordered)" value={data.now.albums_in_progress} hint={`${data.albums.in_progress_without_photos} without any photo`} />
              </div>
              {data.orders.pdf_not_ready.count > 0 ? (
                <div className="border border-amber-300 bg-amber-50 p-3" data-testid="dashboard-pdf-not-ready">
                  <p className="text-sm font-semibold inline-flex items-center gap-1.5">
                    <AlertTriangle size={14} /> {data.orders.pdf_not_ready.count} printed {data.orders.pdf_not_ready.count === 1 ? "album has" : "albums have"} no PDF yet
                  </p>
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
                <p className="text-sm text-emerald-700">Every printed album has its PDF.</p>
              )}
            </Card>

            <div className="grid grid-cols-1 lg:grid-cols-[2fr_3fr] gap-6">
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

              {/* Over time */}
              <Card>
                <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                  <h2 className="text-xs uppercase tracking-widest text-[color:var(--muted)]">Over time · {chosen.source === "weekly" ? "by week" : "by month"}</h2>
                  <div className="flex flex-wrap gap-1.5" role="group" aria-label="Over time">
                    {RANGES.map((r) => (
                      <button key={r.key} type="button" onClick={() => setRange(r.key)} aria-pressed={range === r.key}
                        className={`text-xs border px-2.5 py-1 ${range === r.key ? "border-[color:var(--ink)] bg-[color:var(--ink)] text-[color:var(--paper)]" : "border-ink/20 hover:border-[color:var(--ink)]"}`}>
                        {r.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="grid sm:grid-cols-2 gap-6" data-testid="dashboard-over-time">
                  <OverTimeChart rows={overTime} source={chosen.source} field="orders" label="Orders" />
                  <OverTimeChart rows={overTime} source={chosen.source} field="revenue_cents" label="Revenue" money />
                  <OverTimeChart rows={overTime} source={chosen.source} field="margin_cents" label="Margin" money />
                  <OverTimeChart rows={overTime} source={chosen.source} field="accounts" label="New accounts" />
                </div>
              </Card>
            </div>

            {/* Albums */}
            <div>
              <h2 className="font-serif-display text-2xl tracking-tight pt-2">Albums, last {periodLabel}</h2>
              <p className="text-xs text-[color:var(--muted)] mt-1 flex items-center gap-3">
                <span className="inline-flex items-center gap-1"><span className="inline-block w-3 h-1 bg-ink/25" /> created</span>
                <span className="inline-flex items-center gap-1"><span className="inline-block w-3 h-1 bg-[color:var(--coral)]" /> ordered</span>
              </p>
            </div>
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="dashboard-albums">
              <Card title="Templates">
                <Choices rows={data.albums.templates} label={templateName} name="Template" />
              </Card>
              <Card title="Pages">
                <Choices rows={data.albums.pages} label={(key) => (key === "unknown" ? "Not known" : `${key} pages`)} name="Pages" />
              </Card>
              <Card title="Format and photos">
                <Choices rows={data.albums.sizes} label={(key) => (key === "unknown" ? "Not known" : key)} name="Size" />
                <div className="mt-4">
                  <Choices rows={data.albums.orientations} label={(key) => (key === "unknown" ? "Not known" : capital(key))} name="Orientation" />
                </div>
                <div className="mt-4 pt-4 border-t border-[color:var(--border-soft)]">
                  <Figure
                    label="Photos per album (average)"
                    value={data.albums.photos_per_album.average}
                    hint={data.albums.photos_per_album.albums ? `median ${data.albums.photos_per_album.median} · over ${data.albums.photos_per_album.albums} albums with photos` : "no album with photos yet"}
                  />
                </div>
              </Card>
            </div>

            {/* Orders */}
            <h2 className="font-serif-display text-2xl tracking-tight pt-2">Orders, last {periodLabel}</h2>
            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6" data-testid="dashboard-orders">
              <Card title="Printed or digital">
                <div className="space-y-3">
                  <Figure label="Printed albums" value={data.orders.printed.albums} hint={`${data.orders.printed.copies} ${data.orders.printed.copies === 1 ? "copy" : "copies"} to print`} />
                  <Figure label="Digital albums (PDF)" value={data.orders.digital.albums} />
                </div>
              </Card>
              <Card title="Where they are now">
                <Bars rows={data.orders.by_status} label={(key) => STATUSES[key] || key} />
              </Card>
              <Card title="Delivery areas">
                <Bars rows={data.orders.areas} />
              </Card>
              <Card title="Delivery and customers">
                <div className="space-y-3">
                  <Figure
                    label="Days from order to delivery (average)"
                    value={data.orders.delivery_days.average}
                    hint={data.orders.delivery_days.orders ? `median ${data.orders.delivery_days.median} · ${data.orders.delivery_days.orders} delivered` : "nothing delivered in this period"}
                  />
                  <Figure label="Customers (all time)" value={data.orders.customers} />
                  <Figure label="Ordered again" value={data.orders.repeat_customers} hint={data.orders.customers ? `${pct(data.orders.repeat_customers, data.orders.customers)}% of customers` : null} />
                </div>
              </Card>
            </div>
            <Card title="Promo codes used">
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
            <Card title="Gift cards">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="dashboard-gift-cards">
                <Figure label={`Sold, last ${periodLabel}`} value={data.gift_cards.sold} hint={`${usd(data.gift_cards.sold_cents)} paid`} />
                <Figure label={`Used, last ${periodLabel}`} value={data.gift_cards.redeemed} hint="turned into credit by the person who received it" />
                <Figure label="Not used yet" value={data.gift_cards.unused} hint={`${usd(data.gift_cards.unused_cents)} still to spend`} />
                <Figure label="Expired without being used" value={data.gift_cards.expired_unused} hint={data.gift_cards.waiting_for_payment ? `${data.gift_cards.waiting_for_payment} waiting for payment` : null} />
              </div>
            </Card>
            <p className="text-xs text-[color:var(--muted)]">An order is one cart: it can hold several albums. Cancelled orders are left out of orders, revenue and margin. Albums deleted later still count in albums created.</p>
          </div>
        )}
      </div>
    </main>
  );
}
