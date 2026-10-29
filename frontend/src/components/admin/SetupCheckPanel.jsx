import React, { useEffect, useState } from "react";
import { CheckCircle2, ChevronDown, XCircle } from "lucide-react";
import { api } from "@/lib/api";

/**
 * What's set up on the server (backend /admin/setup-check): each setting
 * there or not, never its value — to check everything before going live.
 * Opened by itself when something's missing.
 */
export default function SetupCheckPanel() {
  const [rows, setRows] = useState(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    api.get("/admin/setup-check").then(({ data }) => {
      setRows(data);
      setOpen(data.some((r) => !r.ok && !/optional/i.test(r.label)));
    }).catch(() => setRows([]));
  }, []);

  if (!rows || rows.length === 0) return null;
  const missing = rows.filter((r) => !r.ok && !/optional/i.test(r.label)).length;
  return (
    <section className="mb-4 border border-[color:var(--border-soft)]" data-testid="admin-setup-check">
      <button type="button" onClick={() => setOpen((o) => !o)} className="w-full flex items-center justify-between px-4 py-3 text-left">
        <span className="inline-flex items-center gap-2 text-sm font-semibold">
          {missing ? <XCircle size={14} className="text-red-600" /> : <CheckCircle2 size={14} className="text-emerald-600" />}
          Setup check {missing ? `— ${missing} to fix` : "— all set"}
        </span>
        <ChevronDown size={16} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <ul className="px-4 pb-4 border-t border-[color:var(--border-soft)] pt-3 space-y-1.5 text-sm">
          {rows.map((r) => (
            <li key={r.key} className="flex items-start gap-2" data-testid={`setup-${r.key}`}>
              {r.ok ? <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-600" /> : <XCircle size={15} className={`mt-0.5 shrink-0 ${/optional/i.test(r.label) ? "text-[color:var(--muted)]" : "text-red-600"}`} />}
              <span>
                {r.label}
                {!r.ok && r.hint && <span className="block text-xs text-[color:var(--muted)]">{r.hint}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
