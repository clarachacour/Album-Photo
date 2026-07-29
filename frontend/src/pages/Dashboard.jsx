import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { TID } from "@/constants/testIds";
import { getCover } from "@/lib/coverTemplates";
import { coverImageUrl } from "@/lib/api";
import { CoverFront } from "@/components/CoverPreview";
import { Plus, Trash2, ArrowUpRight } from "lucide-react";

export default function Dashboard() {
  const [albums, setAlbums] = useState([]);
  const [loading, setLoading] = useState(true);
  const nav = useNavigate();

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/albums");
      setAlbums(data);
    } catch {
      toast.error("Failed to load your albums");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const remove = async (id, title) => {
    if (!window.confirm(`Delete "${title}"?`)) return;
    try {
      await api.delete(`/albums/${id}`);
      toast.success("Album deleted");
      load();
    } catch {
      toast.error("Deletion failed");
    }
  };

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-28 pb-24 px-6 md:px-12">
      <div className="max-w-[1400px] mx-auto">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-16">
          <div>
            <div className="eyebrow mb-3">Library</div>
            <h1 className="font-serif-display text-5xl md:text-6xl tracking-tight">Your editions</h1>
          </div>
          <button
            data-testid={TID.dashCreate}
            onClick={() => nav("/choose-template")}
            className="group inline-flex items-center gap-3 bg-[color:var(--ink)] text-[color:var(--paper)] px-8 py-4 hover:bg-[color:var(--coral)] transition-colors self-start"
          >
            <Plus size={16} />
            <span className="text-sm font-semibold tracking-widest uppercase">New album</span>
          </button>
        </div>

        {loading ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="aspect-[3/4] bg-[color:var(--editor-canvas)] animate-pulse" />
            ))}
          </div>
        ) : albums.length === 0 ? (
          <div className="border border-dashed border-[color:var(--ink)]/20 py-24 px-8 text-center">
            <p className="font-serif-display text-3xl mb-4">No albums yet.</p>
            <p className="text-[color:var(--ink)]/70 mb-8">Create your first edition in a few minutes.</p>
            <button
              onClick={() => nav("/choose-template")}
              className="bg-[color:var(--ink)] text-[color:var(--paper)] px-8 py-4 text-sm font-semibold tracking-widest uppercase hover:bg-[color:var(--coral)] transition-colors"
            >
              Get started
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-8 gap-y-16">
            {albums.map((a) => {
              const cover = getCover(a.cover);
              if (a.cover_image_path) cover.image = coverImageUrl(a.id);
              const isDraft = a.status === "draft";
              const linkTo = isDraft ? `/create?albumId=${a.id}` : `/editor/${a.id}`;
              return (
                <div key={a.id} className="group animate-fade-up" data-testid={TID.albumCard}>
                  <Link to={linkTo} className="block relative">
                    <CoverFront cover={cover} title={a.title || "Untitled"} />
                    <div className="absolute inset-0 opacity-0 group-hover:opacity-100 bg-black/30 flex items-center justify-center transition-opacity">
                      <ArrowUpRight className="text-white" size={32} />
                    </div>
                  </Link>
                  <div className="mt-4 flex items-start justify-between gap-3">
                    <div>
                      <div className="font-serif-display text-xl leading-tight">{a.title}</div>
                      <div className="eyebrow mt-1 text-[color:var(--muted)]">
                        {a.country || "—"} · {a.year} · {a.size} {a.orientation === "landscape" ? "landscape" : "portrait"}
                      </div>
                      <div className="text-xs mt-2 uppercase tracking-widest text-[color:var(--coral)]">
                        {statusLabel(a.status)}
                      </div>
                      <div className="text-xs mt-2 text-[color:var(--muted)] space-y-0.5">
                        <div>Created {formatDate(a.created_at)}</div>
                        <div>Last modified {formatDate(a.updated_at)}</div>
                      </div>
                    </div>
                    <button
                      onClick={() => remove(a.id, a.title)}
                      className="text-[color:var(--muted)] hover:text-red-600 transition-colors"
                      data-testid={`album-delete-${a.id}`}
                      aria-label="Delete"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}

function statusLabel(s) {
  switch (s) {
    case "draft":
      return "Draft";
    case "processing":
      return "AI processing";
    case "ready":
      return "Ready";
    case "error":
      return "Error";
    default:
      return s || "—";
  }
}

function formatDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return "—";
  }
}