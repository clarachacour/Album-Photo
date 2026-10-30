import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { ChevronDown, Trash2 } from "lucide-react";
import { api } from "@/lib/api";

/**
 * ONE-TIME TOOL — deleting the test accounts and orders made before the
 * launch (backend routers/test_cleanup.py). Remove both once done.
 * Each deletion is confirmed by typing the account's email (or the order's
 * number) again; the admin account can't be deleted.
 */
export default function TestCleanupPanel() {
  const [open, setOpen] = useState(false);
  const [accounts, setAccounts] = useState(null);
  const [orders, setOrders] = useState(null);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState("");

  const load = () => {
    api.get("/admin/test-cleanup/accounts").then(({ data }) => setAccounts(data)).catch(() => setAccounts([]));
    api.get("/admin/test-cleanup/orders").then(({ data }) => setOrders(data)).catch(() => setOrders([]));
  };
  useEffect(() => {
    if (open && !accounts) load();
  }, [open, accounts]);

  const deleteAccount = async (a) => {
    const typed = window.prompt(
      `Delete ${a.email} for good — the account, its ${a.albums} album(s), photos and ${a.orders} order(s)?\n\nType the email to confirm:`
    );
    if (!typed) return;
    setBusy(a.id);
    try {
      await api.post(`/admin/test-cleanup/accounts/${a.id}/delete`, { confirm: typed });
      toast.success(`${a.email} deleted`);
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't delete it");
    } finally {
      setBusy("");
    }
  };

  const deleteOrder = async (o) => {
    const typed = window.prompt(`Delete order ${o.number} (${o.album_title || "Album"}) for good, with its PDF and album?\n\nType the order number to confirm:`);
    if (!typed) return;
    setBusy(o.id);
    try {
      await api.post(`/admin/test-cleanup/orders/${o.id}/delete`, { confirm: typed });
      toast.success(`Order ${o.number} deleted`);
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't delete it");
    } finally {
      setBusy("");
    }
  };

  const shown = (accounts || []).filter((a) => !search || `${a.email} ${a.name || ""}`.toLowerCase().includes(search.toLowerCase()));
  const cell = "py-2 pr-3";
  return (
    <section className="mb-8 border border-red-200" data-testid="admin-test-cleanup">
      <button type="button" onClick={() => setOpen((o) => !o)} className="w-full flex items-center justify-between px-4 py-3 text-left">
        <span className="inline-flex items-center gap-2 text-sm font-semibold text-red-700"><Trash2 size={14} /> Delete test data (one time, before launch)</span>
        <ChevronDown size={16} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="px-4 pb-4 border-t border-red-200 text-sm">
          <p className="text-xs text-[color:var(--muted)] py-3">
            Deletes for good, files included (photos, PDFs). No email is sent. Your admin account can't be deleted here.
          </p>
          <div className="flex items-center justify-between gap-3 mb-2">
            <div className="eyebrow">Accounts ({accounts ? accounts.length : "…"})</div>
            <input className="border border-ink/20 px-2 py-1 text-sm w-64" placeholder="Search an email or a name" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <div className="max-h-[420px] overflow-y-auto border border-[color:var(--border-soft)] mb-6">
            <table className="w-full">
              <thead>
                <tr className="text-left text-xs uppercase tracking-widest text-[color:var(--muted)] border-b border-[color:var(--border-soft)]">
                  <th className={`${cell} pl-3`}>Email</th><th className={cell}>Name</th><th className={cell}>Signed up</th><th className={cell}>Albums</th><th className={cell}>Orders</th><th className={cell}></th>
                </tr>
              </thead>
              <tbody>
                {shown.map((a) => (
                  <tr key={a.id} className="border-b border-[color:var(--border-soft)] last:border-0" data-testid={`cleanup-account-${a.email}`}>
                    <td className={`${cell} pl-3`}>{a.email}</td>
                    <td className={cell}>{a.name}</td>
                    <td className={cell}>{(a.created_at || "").slice(0, 10)}</td>
                    <td className={cell}>{a.albums}</td>
                    <td className={cell}>{a.orders}</td>
                    <td className={`${cell} text-right`}>
                      {a.is_admin ? (
                        <span className="text-xs text-[color:var(--muted)]">your admin account</span>
                      ) : (
                        <button type="button" disabled={busy === a.id} onClick={() => deleteAccount(a)} className="text-xs border border-red-300 text-red-700 px-2 py-1 hover:bg-red-50 disabled:opacity-50">
                          Delete
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="eyebrow mb-1">Cancelled orders ({orders ? orders.length : "…"})</div>
          <p className="text-xs text-[color:var(--muted)] mb-2">Your own test orders: cancel them in the list below first, then delete them here.</p>
          <ul className="border border-[color:var(--border-soft)] divide-y divide-[color:var(--border-soft)]">
            {(orders || []).map((o) => (
              <li key={o.id} className="flex items-center justify-between px-3 py-2">
                <span><span className="font-mono">{o.number}</span> — {o.album_title || "Album"} {o.shipping_address?.full_name ? `· ${o.shipping_address.full_name}` : ""}</span>
                <button type="button" disabled={busy === o.id} onClick={() => deleteOrder(o)} className="text-xs border border-red-300 text-red-700 px-2 py-1 hover:bg-red-50 disabled:opacity-50">
                  Delete
                </button>
              </li>
            ))}
            {orders && orders.length === 0 && <li className="px-3 py-2 text-[color:var(--muted)]">No cancelled order.</li>}
          </ul>
        </div>
      )}
    </section>
  );
}
