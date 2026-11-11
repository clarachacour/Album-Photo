import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { ChevronDown, Printer } from "lucide-react";
import { api } from "@/lib/api";

/**
 * Which file the printer gets (backend services/print_format.py): the
 * original layout, or the one-sheet hardcover format. Applies to the PDFs
 * made from now on; regenerate an order's PDF to get the other format.
 */
const FORMATS = {
  bookstop: {
    label: "Original (Bookstop)",
    help: "Spine and front cover on the first sheet, the pages, the back cover on the last sheet.",
  },
  hardcover: {
    label: "One-sheet hardcover (new printer)",
    help: "Back cover, spine and front cover on one sheet with a 20 mm wrap, 5 mm bleed and crop marks; each page on white with a 3 mm bleed and crop marks.",
  },
};

export default function PrintFormatPanel() {
  const [open, setOpen] = useState(false);
  const [format, setFormat] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || format) return;
    api.get("/admin/print-format").then(({ data }) => setFormat(data.format)).catch(() => setFormat("bookstop"));
  }, [open, format]);

  const choose = async (value) => {
    if (value === format || busy) return;
    setBusy(true);
    try {
      const { data } = await api.put("/admin/print-format", { format: value });
      setFormat(data.format);
      toast.success(`New PDFs: ${FORMATS[data.format].label}`);
    } catch {
      toast.error("Couldn't change the format");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mb-8 border border-[color:var(--border-soft)]" data-testid="admin-print-format">
      <button type="button" onClick={() => setOpen((o) => !o)} className="w-full flex items-center justify-between px-4 py-3 text-left">
        <span className="inline-flex items-center gap-2 text-sm font-semibold">
          <Printer size={14} /> Printer file format{format && <span className="font-normal text-[color:var(--muted)]">· {FORMATS[format].label}</span>}
        </span>
        <ChevronDown size={16} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="px-4 pb-4 border-t border-[color:var(--border-soft)] pt-3 space-y-2">
          {Object.entries(FORMATS).map(([value, f]) => (
            <label key={value} className="flex items-start gap-2 text-sm cursor-pointer">
              <input type="radio" name="print-format" checked={format === value} onChange={() => choose(value)} disabled={busy || !format} className="mt-1" data-testid={`print-format-${value}`} />
              <span>
                <span className="font-medium">{f.label}</span>
                <span className="block text-xs text-[color:var(--muted)]">{f.help}</span>
              </span>
            </label>
          ))}
          <p className="text-xs text-[color:var(--muted)] pt-1">For the PDFs made from now on. A PDF already made stays as it is: use "Regenerate PDF" on an order to get it in the other format.</p>
        </div>
      )}
    </section>
  );
}
