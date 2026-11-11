import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, FileCheck2, Loader2 } from "lucide-react";
import { api, adminTestPdfUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { parseDate } from "@/lib/dates";

/**
 * In the album editor, for the admin only: a test PDF of this album in the
 * one-sheet hardcover format (backend services/test_pdf.py), to send a
 * printer. No order is made and nothing goes to the printer. Shown to no
 * one else (the server refuses anyone but the admin too).
 */
export default function TestPdfPanel({ albumId, beforeMake }) {
  const { user } = useAuth();
  const isAdmin = !!user?.is_admin;
  const [state, setState] = useState(null);

  useEffect(() => {
    if (!isAdmin || !albumId) return undefined;
    let stop = false;
    let timer;
    const check = () =>
      api
        .get(`/admin/albums/${albumId}/test-pdf`)
        .then(({ data }) => {
          if (stop) return;
          setState(data);
          if (data.status === "making") timer = setTimeout(check, 5000);
        })
        .catch(() => !stop && setState({ status: "none" }));
    check();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [isAdmin, albumId, state?.status === "making"]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!isAdmin) return null;

  const make = async () => {
    // The PDF is made from the saved album: save the edits first.
    if (beforeMake && !(await beforeMake())) return;
    setState({ status: "making" });
    try {
      const { data } = await api.post(`/admin/albums/${albumId}/test-pdf`);
      setState(data);
    } catch {
      setState({ status: "failed" });
      toast.error("Couldn't start the test PDF");
    }
  };

  const making = state?.status === "making";
  return (
    <div className="border-t border-[color:var(--border-soft)] pt-6 mt-6" data-testid="admin-test-pdf">
      <div className="eyebrow mb-1">Admin · printer test</div>
      <p className="text-xs text-[color:var(--muted)] mb-3">
        A PDF of this album in the new one-sheet hardcover format. No order, nothing sent to the printer. Only you see this.
      </p>
      <button
        type="button"
        onClick={make}
        disabled={making}
        className="w-full inline-flex items-center justify-center gap-2 border border-ink/30 px-3 py-2 text-xs font-semibold tracking-widest uppercase hover:border-[color:var(--ink)] disabled:opacity-60"
        data-testid="admin-test-pdf-make"
      >
        {making ? <Loader2 size={13} className="animate-spin" /> : <FileCheck2 size={13} />}
        {making ? "Making the PDF…" : state?.status === "ready" ? "Make it again" : "Make a test PDF"}
      </button>
      {making && <p className="text-xs text-[color:var(--muted)] mt-2">About 2 to 3 seconds a page. You can leave this page and come back.</p>}
      {state?.status === "ready" && (
        <a href={adminTestPdfUrl(albumId)} className="mt-2 w-full inline-flex items-center justify-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] px-3 py-2 text-xs font-semibold tracking-widest uppercase hover:bg-[color:var(--coral)]" data-testid="admin-test-pdf-download">
          <Download size={13} /> Download ({state.pages} {state.pages === 1 ? "page" : "pages"}, {parseDate(state.made_at)?.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })})
        </a>
      )}
      {state?.status === "failed" && <p className="text-xs text-red-700 mt-2">The test PDF failed{state.error ? `: ${state.error}` : ""}. Try again.</p>}
    </div>
  );
}
