import React, { useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Search } from "lucide-react";

/**
 * Admin-only diagnostic: for one album (typed in by id), lists every page
 * slot whose photo was deleted (or otherwise went missing) — with the
 * original filename and capture date still on record, since that's what's
 * actually useful for finding the right file to re-upload once the R2
 * file itself is gone for good.
 */
export default function AdminBrokenPhotosPage() {
  const [albumId, setAlbumId] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [forbidden, setForbidden] = useState(false);

  const check = async (e) => {
    e.preventDefault();
    if (!albumId.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const { data } = await api.get(`/admin/albums/${albumId.trim()}/broken-photos`);
      setResult(data);
    } catch (err) {
      if (err?.response?.status === 403) {
        setForbidden(true);
      } else {
        toast.error(err?.response?.data?.detail || "Failed to check this album");
      }
    } finally {
      setLoading(false);
    }
  };

  if (forbidden) {
    return (
      <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
        <div className="max-w-[600px] mx-auto text-center">
          <h1 className="font-serif-display text-3xl tracking-tight mb-3">Not available</h1>
          <p className="text-[color:var(--ink)]/70">This page is only visible to the account running the business.</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
      <div className="max-w-[900px] mx-auto">
        <h1 className="font-serif-display text-4xl tracking-tight mb-2">Missing photos</h1>
        <p className="text-sm text-[color:var(--ink)]/60 mb-8">Paste an album id to see which of its photos need re-uploading.</p>

        <form onSubmit={check} className="flex gap-2 mb-10">
          <input
            type="text"
            value={albumId}
            onChange={(e) => setAlbumId(e.target.value)}
            placeholder="Album id (from the editor's URL)"
            className="flex-1 px-4 py-2.5 border border-[color:var(--ink)]/30 focus:border-[color:var(--ink)] outline-none text-sm font-mono"
          />
          <button
            type="submit"
            disabled={loading}
            className="inline-flex items-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] px-5 py-2.5 hover:bg-[color:var(--coral)] transition-colors disabled:opacity-60 text-sm font-semibold uppercase tracking-widest"
          >
            <Search size={14} />
            {loading ? "…" : "Check"}
          </button>
        </form>

        {result && (
          <div>
            <h2 className="font-serif-display text-2xl tracking-tight mb-1">{result.album_title}</h2>
            <p className="text-sm text-[color:var(--ink)]/60 mb-6">{result.total_pages} pages checked</p>

            {result.broken.length === 0 ? (
              <p className="text-sm text-emerald-700">Nothing missing — every photo in this album is intact.</p>
            ) : (
              <div className="border border-[color:var(--border-soft)]">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left border-b border-[color:var(--border-soft)] text-xs uppercase tracking-widest text-[color:var(--muted)]">
                      <th className="p-3">Page</th>
                      <th className="p-3">Original filename</th>
                      <th className="p-3">Taken on</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.broken.map((b, i) => (
                      <tr key={i} className="border-b border-[color:var(--border-soft)] last:border-0">
                        <td className="p-3 whitespace-nowrap">Page {b.page_index + 1}</td>
                        <td className="p-3 font-mono">{b.original_filename || "— (no record at all)"}</td>
                        <td className="p-3 text-[color:var(--ink)]/70">
                          {b.taken_at ? new Date(b.taken_at).toLocaleDateString() : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
