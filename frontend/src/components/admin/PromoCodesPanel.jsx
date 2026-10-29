import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { ChevronDown, Plus, Tag } from "lucide-react";
import { api } from "@/lib/api";

/**
 * Promo codes, in the admin (backend routers/promo_codes.py): a percentage
 * off the albums (not the delivery), once per customer, until a last day
 * (optional). A code can be switched off and on; how many times it was
 * used is shown.
 */
export default function PromoCodesPanel() {
  const [open, setOpen] = useState(false);
  const [codes, setCodes] = useState(null);
  const [form, setForm] = useState({ code: "", percent: 10, ends_on: "" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || codes) return;
    api.get("/admin/promo-codes").then(({ data }) => setCodes(data)).catch(() => setCodes([]));
  }, [open, codes]);

  const replace = (updated) => setCodes((list) => list.map((c) => (c.code === updated.code ? updated : c)));

  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/admin/promo-codes", { code: form.code, percent: Number(form.percent), ends_on: form.ends_on || null });
      setCodes((list) => [data, ...(list || [])]);
      setForm({ code: "", percent: 10, ends_on: "" });
      toast.success(`Code ${data.code} created`);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Check the code (3 to 30 letters, digits or dashes) and the percentage (1 to 100)");
    } finally {
      setBusy(false);
    }
  };

  const update = async (code, changes) => {
    try {
      const { data } = await api.patch(`/admin/promo-codes/${encodeURIComponent(code)}`, changes);
      replace(data);
    } catch {
      toast.error("Couldn't save the change");
    }
  };

  const today = new Date().toISOString().slice(0, 10);
  const input = "border border-ink/20 px-2 py-1.5 text-sm bg-white focus:border-[color:var(--ink)] focus:outline-none";

  return (
    <section className="mb-8 border border-[color:var(--border-soft)]" data-testid="admin-promo-codes">
      <button type="button" onClick={() => setOpen((o) => !o)} className="w-full flex items-center justify-between px-4 py-3 text-left">
        <span className="inline-flex items-center gap-2 text-sm font-semibold"><Tag size={14} /> Promo codes</span>
        <ChevronDown size={16} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="px-4 pb-4 border-t border-[color:var(--border-soft)]">
          <form onSubmit={create} className="flex flex-wrap items-end gap-3 py-4">
            <label className="text-xs text-[color:var(--muted)]">
              Code
              <input className={`${input} block uppercase w-40`} value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} placeholder="WELCOME10" required data-testid="promo-new-code" />
            </label>
            <label className="text-xs text-[color:var(--muted)]">
              % off the albums
              <input className={`${input} block w-24`} type="number" min={1} max={100} value={form.percent} onChange={(e) => setForm({ ...form, percent: e.target.value })} required data-testid="promo-new-percent" />
            </label>
            <label className="text-xs text-[color:var(--muted)]">
              Last day (optional)
              <input className={`${input} block`} type="date" min={today} value={form.ends_on} onChange={(e) => setForm({ ...form, ends_on: e.target.value })} data-testid="promo-new-ends" />
            </label>
            <button type="submit" disabled={busy} className="inline-flex items-center gap-1.5 bg-[color:var(--ink)] text-[color:var(--paper)] px-4 py-2 text-xs font-semibold tracking-widest uppercase hover:bg-[color:var(--coral)] transition-colors disabled:opacity-50" data-testid="promo-create">
              <Plus size={13} /> Create
            </button>
          </form>
          <p className="text-xs text-[color:var(--muted)] mb-3">Off the albums only (not the delivery). Each customer can use a code once.</p>
          {!codes ? (
            <p className="text-sm text-[color:var(--muted)]">Loading…</p>
          ) : codes.length === 0 ? (
            <p className="text-sm text-[color:var(--muted)]">No promo codes yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-widest text-[color:var(--muted)] border-b border-[color:var(--border-soft)]">
                  <th className="py-2 pr-3">Code</th>
                  <th className="py-2 pr-3">Discount</th>
                  <th className="py-2 pr-3">Last day</th>
                  <th className="py-2 pr-3">Used</th>
                  <th className="py-2 pr-3">State</th>
                </tr>
              </thead>
              <tbody>
                {codes.map((c) => {
                  const expired = c.ends_on && c.ends_on < today;
                  return (
                    <tr key={c.code} className="border-b border-[color:var(--border-soft)] last:border-0" data-testid={`promo-row-${c.code}`}>
                      <td className="py-2 pr-3 font-mono font-semibold">{c.code}</td>
                      <td className="py-2 pr-3">−{c.percent}%</td>
                      <td className="py-2 pr-3">
                        <input type="date" className={input} value={c.ends_on || ""} onChange={(e) => update(c.code, { ends_on: e.target.value || null })} />
                      </td>
                      <td className="py-2 pr-3">{c.uses} {c.uses === 1 ? "time" : "times"}</td>
                      <td className="py-2 pr-3">
                        <button
                          type="button"
                          onClick={() => update(c.code, { active: !c.active })}
                          className={`text-xs border px-2 py-1 ${c.active && !expired ? "border-emerald-600 text-emerald-700" : "border-ink/30 text-[color:var(--muted)]"}`}
                          title={c.active ? "Click to switch it off" : "Click to switch it on"}
                        >
                          {!c.active ? "Off" : expired ? "Ended" : "On"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </section>
  );
}
