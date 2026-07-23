import React, { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { api, pdfExportUrl, coverImageUrl, photoImageUrl } from "@/lib/api";
import { toast } from "sonner";
import { getTemplate } from "@/lib/coverTemplates";
import { AlbumPage, CoverFrontPage, CoverBackPage } from "@/components/AlbumPage";
import Flipbook from "@/components/Flipbook";
import PhotoTray from "@/components/PhotoTray";
import { TID } from "@/constants/testIds";
import { ChevronLeft, ChevronRight, Download, Save, Sparkles, Type, Trash2, Loader2, ArrowLeft, Image as ImageIcon, X as XIcon, ZoomIn, Move, Bold, Italic, Palette, Square, Circle as CircleIcon, ClipboardPaste } from "lucide-react";

const FONT_OPTIONS = [
  { label: "Cormorant (serif)", value: "'Cormorant Garamond', serif" },
  { label: "Manrope (sans)", value: "'Manrope', sans-serif" },
  { label: "Georgia", value: "Georgia, serif" },
  { label: "Courier", value: "'Courier New', monospace" },
  { label: "Helvetica", value: "Helvetica, Arial, sans-serif" },
];

const COLOR_SWATCHES = ["#1A1A17", "#F9F8F6", "#E56B55", "#0F5A67", "#2C402E", "#C9A959", "#1C2D42"];

export default function AlbumEditor() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const bookRef = useRef();
  const coverInputRef = useRef();
  const [album, setAlbum] = useState(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [selected, setSelected] = useState(null); // {pageIdx, item}
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [uploadingCover, setUploadingCover] = useState(false);
  const [coverVersion, setCoverVersion] = useState(0);
  const [processing, setProcessing] = useState(params.get("processing") === "1");
  // Cover-related selection: {mode: "cover" | "title" | "item", itemId?}
  const [coverSel, setCoverSel] = useState(null);

  // Load album
  const loadAlbum = useCallback(async () => {
    try {
      const { data } = await api.get(`/albums/${id}`);
      setAlbum(data);
      if (data.status === "processing") setProcessing(true);
      else setProcessing(false);
    } catch {
      toast.error("Impossible de charger cet album");
      nav("/dashboard");
    }
  }, [id, nav]);

  useEffect(() => {
    loadAlbum();
  }, [loadAlbum]);

  // Handle paste event: if a cover selection is active, paste text as a new cover text element
  useEffect(() => {
    const onPaste = (e) => {
      if (!coverSel) return;
      // Skip if focus is in an input/textarea
      const tag = document.activeElement?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea") return;
      const text = e.clipboardData?.getData("text/plain");
      if (text && text.trim()) {
        e.preventDefault();
        addCoverText(text.trim().slice(0, 500));
      }
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [coverSel]);

  // Poll while processing
  useEffect(() => {
    if (!processing) return;
    const interval = setInterval(async () => {
      try {
        const { data } = await api.get(`/albums/${id}/status`);
        if (data.status !== "processing") {
          setProcessing(false);
          loadAlbum();
          if (data.status === "ready") toast.success("Album prêt");
          if (data.status === "error") toast.error("Erreur lors du traitement IA");
        }
      } catch {
        /* noop */
      }
    }, 2500);
    return () => clearInterval(interval);
  }, [processing, id, loadAlbum]);

  const template = album ? getTemplate(album.cover_template_id) : null;
  const orientation = album?.orientation || "portrait";

  const save = async () => {
    if (!album) return;
    setSaving(true);
    try {
      await api.patch(`/albums/${id}`, { pages: album.pages, cover: album.cover || {} });
      toast.success("Enregistré");
    } catch {
      toast.error("Enregistrement impossible");
    } finally {
      setSaving(false);
    }
  };

  const exportPdf = async () => {
    setExporting(true);
    try {
      // Open in new tab with token query param
      const url = pdfExportUrl(id);
      window.open(url, "_blank");
    } finally {
      setTimeout(() => setExporting(false), 1200);
    }
  };

  const updateSelectedItem = (patch) => {
    if (!selected) return;
    const { pageIdx, item } = selected;
    const newPages = [...album.pages];
    newPages[pageIdx] = {
      ...newPages[pageIdx],
      items: newPages[pageIdx].items.map((it) => (it.id === item.id ? { ...it, ...patch } : it)),
    };
    setAlbum({ ...album, pages: newPages });
    setSelected({ pageIdx, item: { ...item, ...patch } });
  };

  // Update any item on a page by id (used by drag/resize handlers)
  const updateItemById = (pageIdx, itemId, patch) => {
    setAlbum((prev) => {
      if (!prev) return prev;
      const newPages = [...prev.pages];
      newPages[pageIdx] = {
        ...newPages[pageIdx],
        items: newPages[pageIdx].items.map((it) => (it.id === itemId ? { ...it, ...patch } : it)),
      };
      return { ...prev, pages: newPages };
    });
    setSelected((prev) => (prev && prev.item?.id === itemId ? { ...prev, item: { ...prev.item, ...patch } } : prev));
  };

  // Cover editing helpers
  const updateCover = (patch) => {
    setAlbum((prev) => ({ ...prev, cover: { ...(prev.cover || {}), ...patch } }));
  };

  const updateCoverItem = (itemId, patch) => {
    setAlbum((prev) => {
      const cover = prev.cover || {};
      const items = (cover.extra_items || []).map((it) => (it.id === itemId ? { ...it, ...patch } : it));
      return { ...prev, cover: { ...cover, extra_items: items } };
    });
    setCoverSel((prev) => (prev && prev.mode === "item" && prev.itemId === itemId ? { ...prev } : prev));
  };

  const addCoverText = (content = "Nouveau texte") => {
    const newItem = {
      id: cryptoRandom(),
      type: "text",
      content,
      x: 0.1,
      y: 0.5,
      w: 0.5,
      h: 0.08,
      font: "'Manrope', sans-serif",
      color: album?.cover?.text_color || "#F9F8F6",
      font_size: 22,
      font_weight: "normal",
    };
    setAlbum((prev) => {
      const cover = prev.cover || {};
      return { ...prev, cover: { ...cover, extra_items: [...(cover.extra_items || []), newItem] } };
    });
    setCoverSel({ mode: "item", itemId: newItem.id });
    toast.success("Texte ajouté à la couverture");
  };

  const addCoverShape = (shape_type = "rect") => {
    const newItem = {
      id: cryptoRandom(),
      type: "shape",
      shape_type,
      x: 0.3,
      y: 0.6,
      w: 0.15,
      h: 0.15,
      fill_color: album?.cover?.accent_color || "#E56B55",
    };
    setAlbum((prev) => {
      const cover = prev.cover || {};
      return { ...prev, cover: { ...cover, extra_items: [...(cover.extra_items || []), newItem] } };
    });
    setCoverSel({ mode: "item", itemId: newItem.id });
    toast.success("Forme ajoutée");
  };

  const removeCoverItem = (itemId) => {
    setAlbum((prev) => {
      const cover = prev.cover || {};
      return {
        ...prev,
        cover: {
          ...cover,
          extra_items: (cover.extra_items || []).filter((it) => it.id !== itemId),
        },
      };
    });
    setCoverSel(null);
  };

  const addTextToCurrentPage = () => {
    if (!album || !album.pages || album.pages.length === 0) return;
    // pageIndex is the current spread number.
    // Spread 0 = cover front + blank. Spread 1 = content pages [0]+[1]. Target the right page (content page 2*spread-1).
    let targetIdx = pageIndex >= 1 ? pageIndex * 2 - 1 : 0;
    targetIdx = Math.min(Math.max(targetIdx, 0), album.pages.length - 1);
    const newItem = {
      id: cryptoRandom(),
      type: "text",
      content: "Votre légende",
      x: 0.08,
      y: 0.86,
      w: 0.6,
      h: 0.08,
      font: "'Cormorant Garamond', serif",
      color: "#1A1A17",
      font_size: 24,
    };
    const newPages = [...album.pages];
    newPages[targetIdx] = { ...newPages[targetIdx], items: [...newPages[targetIdx].items, newItem] };
    setAlbum({ ...album, pages: newPages });
    setSelected({ pageIdx: targetIdx, item: newItem });
    toast.success(`Texte ajouté à la page ${targetIdx + 1}`);
  };

  const removeSelected = () => {
    if (!selected) return;
    const { pageIdx, item } = selected;
    const newPages = [...album.pages];
    newPages[pageIdx] = {
      ...newPages[pageIdx],
      items: newPages[pageIdx].items.filter((it) => it.id !== item.id),
    };
    setAlbum({ ...album, pages: newPages });
    setSelected(null);
  };

  const uploadCoverImage = async (file) => {
    if (!file) return;
    setUploadingCover(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post(`/albums/${id}/cover-image`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setAlbum({ ...album, cover_image_path: data.cover_image_path });
      setCoverVersion((v) => v + 1);
      toast.success("Image de couverture ajoutée");
    } catch {
      toast.error("Upload impossible");
    } finally {
      setUploadingCover(false);
    }
  };

  const removeCoverImage = async () => {
    setUploadingCover(true);
    try {
      await api.delete(`/albums/${id}/cover-image`);
      setAlbum({ ...album, cover_image_path: null });
      setCoverVersion((v) => v + 1);
      toast.success("Image retirée");
    } catch {
      toast.error("Suppression impossible");
    } finally {
      setUploadingCover(false);
    }
  };

  // Reorder photos across all pages while preserving each page's layout slot count.
  // sequence = new global order of photo_ids across all page slots.
  const reorderPhotoSequence = (newPhotoIdSequence) => {
    const newPages = [];
    let idx = 0;
    for (const p of album.pages) {
      const newItems = p.items.map((it) => {
        if (it.type !== "photo") return it;
        const newPhotoId = newPhotoIdSequence[idx] ?? it.photo_id;
        idx += 1;
        return { ...it, photo_id: newPhotoId };
      });
      newPages.push({ ...p, items: newItems });
    }
    setAlbum({ ...album, pages: newPages });
  };

  // Flatten photo slots from pages (only photo items) into a sequence
  const photoSequence = () => {
    const seq = [];
    for (const p of album?.pages || []) {
      for (const it of p.items || []) {
        if (it.type === "photo") seq.push(it.photo_id);
      }
    }
    return seq;
  };

  // Loading + processing states
  if (!album) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[color:var(--editor-canvas)]">
        <p className="eyebrow animate-slow-pulse">Chargement de l'album…</p>
      </div>
    );
  }

  if (processing) {
    return <ProcessingScreen title={album.title} />;
  }

  return (
    <main className="min-h-screen bg-[color:var(--editor-canvas)] pt-20 pb-24 relative">
      <div className="absolute inset-0 grain pointer-events-none" />

      <div className="max-w-[1600px] mx-auto px-4 md:px-8 grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6 items-start">
        {/* Book area */}
        <div className="flex flex-col items-center pt-6">
          <div className="w-full max-w-2xl mb-8 flex items-center justify-between">
            <button
              onClick={() => nav("/dashboard")}
              className="inline-flex items-center gap-2 text-sm text-[color:var(--ink)]/70 hover:text-[color:var(--ink)]"
              data-testid="editor-back"
            >
              <ArrowLeft size={14} /> Bibliothèque
            </button>
            <h1 className="font-serif-display text-2xl truncate">{album.title}</h1>
            <div />
          </div>

          <BookRenderer
            album={album}
            template={template}
            orientation={orientation}
            bookRef={bookRef}
            onSelectItem={(pageIdx, item) => {
              setSelected({ pageIdx, item });
              setCoverSel(null);
            }}
            onUpdateItem={updateItemById}
            selectedId={selected?.item?.id}
            onFlip={(p) => {
              setPageIndex(p);
              // Auto-clear cover selection when leaving cover spread
              if (p !== 0) setCoverSel(null);
            }}
            coverImageUrl={album.cover_image_path ? coverImageUrl(id, coverVersion) : null}
            coverSel={coverSel}
            onSelectCover={() => { setSelected(null); setCoverSel({ mode: "cover" }); }}
            onSelectCoverTitle={() => { setSelected(null); setCoverSel({ mode: "title" }); }}
            onSelectCoverItem={(item) => { setSelected(null); setCoverSel({ mode: "item", itemId: item.id }); }}
            onUpdateCoverTitle={(patch) => updateCover(patch)}
            onUpdateCoverItem={updateCoverItem}
          />

          <div className="flex items-center gap-4 mt-8">
            <button
              data-testid={TID.editorPrev}
              onClick={() => bookRef.current?.pageFlip()?.flipPrev()}
              className="p-3 border border-[color:var(--ink)]/20 hover:bg-white transition-colors"
              aria-label="Page précédente"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="eyebrow">Double-page {pageIndex + 1}</span>
            <button
              data-testid={TID.editorNext}
              onClick={() => bookRef.current?.pageFlip()?.flipNext()}
              className="p-3 border border-[color:var(--ink)]/20 hover:bg-white transition-colors"
              aria-label="Page suivante"
            >
              <ChevronRight size={16} />
            </button>
          </div>

          {/* Photo Tray for reordering */}
          {album.pages && album.pages.length > 0 && (
            <div className="w-full mt-12 max-w-4xl">
              <div className="eyebrow mb-3 text-center">Réorganiser les photos · glissez-déposez</div>
              <PhotoTray
                photoIds={photoSequence()}
                onReorder={reorderPhotoSequence}
              />
            </div>
          )}
        </div>

        {/* Sidebar */}
        <aside className="lg:sticky lg:top-24 bg-white p-6 border border-[color:var(--border-soft)]">
          <div className="eyebrow mb-4">Outils</div>

          <div className="space-y-3 mb-6">
            <button
              data-testid={TID.editorSave}
              onClick={save}
              disabled={saving}
              className="w-full inline-flex items-center justify-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] py-3 hover:bg-[color:var(--coral)] transition-colors disabled:opacity-60"
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
              <span className="text-sm font-semibold tracking-widest uppercase">Enregistrer</span>
            </button>
            <button
              data-testid={TID.editorExportPdf}
              onClick={exportPdf}
              disabled={exporting}
              className="w-full inline-flex items-center justify-center gap-2 border border-[color:var(--ink)] py-3 hover:bg-[color:var(--ink)] hover:text-[color:var(--paper)] transition-colors disabled:opacity-60"
            >
              {exporting ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
              <span className="text-sm font-semibold tracking-widest uppercase">Export PDF</span>
            </button>
            <button
              data-testid={TID.editorAddText}
              onClick={addTextToCurrentPage}
              className="w-full inline-flex items-center justify-center gap-2 border border-[color:var(--ink)]/30 py-3 hover:border-[color:var(--ink)] transition-colors"
            >
              <Type size={14} />
              <span className="text-sm font-semibold tracking-widest uppercase">Ajouter texte</span>
            </button>

            {/* Cover image upload */}
            <div className="pt-2">
              <input
                ref={coverInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                data-testid="editor-cover-input"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) uploadCoverImage(f);
                  e.target.value = "";
                }}
              />
              {!album.cover_image_path ? (
                <button
                  data-testid="editor-cover-upload"
                  onClick={() => coverInputRef.current?.click()}
                  disabled={uploadingCover}
                  className="w-full inline-flex items-center justify-center gap-2 border border-[color:var(--ink)]/30 py-3 hover:border-[color:var(--ink)] transition-colors disabled:opacity-60"
                >
                  {uploadingCover ? <Loader2 size={14} className="animate-spin" /> : <ImageIcon size={14} />}
                  <span className="text-sm font-semibold tracking-widest uppercase">Image de couverture</span>
                </button>
              ) : (
                <div className="flex gap-2">
                  <button
                    data-testid="editor-cover-replace"
                    onClick={() => coverInputRef.current?.click()}
                    disabled={uploadingCover}
                    className="flex-1 inline-flex items-center justify-center gap-2 border border-[color:var(--ink)]/30 py-2 hover:border-[color:var(--ink)] transition-colors text-xs font-semibold tracking-widest uppercase"
                  >
                    <ImageIcon size={12} /> Remplacer
                  </button>
                  <button
                    data-testid="editor-cover-remove"
                    onClick={removeCoverImage}
                    disabled={uploadingCover}
                    className="inline-flex items-center justify-center gap-2 border border-red-300 text-red-600 py-2 px-3 hover:bg-red-50 transition-colors"
                    aria-label="Retirer l'image de couverture"
                  >
                    <XIcon size={12} />
                  </button>
                </div>
              )}
            </div>
          </div>

          <div className="border-t border-[color:var(--border-soft)] pt-6">
            <div className="eyebrow mb-4">Édition</div>
            {coverSel ? (
              <CoverEditorPanel
                album={album}
                coverSel={coverSel}
                updateCover={updateCover}
                updateCoverItem={updateCoverItem}
                addCoverText={addCoverText}
                addCoverShape={addCoverShape}
                removeCoverItem={removeCoverItem}
                onDismiss={() => setCoverSel(null)}
              />
            ) : selected ? (
              selected.item.type === "text" ? (
                <TextEditor item={selected.item} onChange={updateSelectedItem} onRemove={removeSelected} />
              ) : (
                <PhotoEditor item={selected.item} onChange={updateSelectedItem} onRemove={removeSelected} />
              )
            ) : (
              <p className="text-xs text-[color:var(--muted)] leading-relaxed">
                Cliquez sur un élément pour l'éditer. Sur la couverture, cliquez sur le fond, le titre ou un élément ajouté pour ouvrir ses réglages.<br /><br />
                <em>Astuce</em> : déplacez et redimensionnez chaque élément à la souris directement dans le livre.
              </p>
            )}
          </div>

          <div className="border-t border-[color:var(--border-soft)] pt-6 mt-6">
            <div className="eyebrow mb-3">À propos</div>
            <div className="text-sm text-[color:var(--ink)]/70 space-y-1">
              <div>{album.pages?.length || 0} pages</div>
              <div>{album.photos?.filter((p) => p.is_selected).length || 0} photos utilisées</div>
              <div>Format : {album.size} · {orientation}</div>
            </div>
          </div>
        </aside>
      </div>
    </main>
  );
}

// ---------- Book Renderer ----------
function BookRenderer({
  album,
  template,
  orientation,
  bookRef,
  onSelectItem,
  onUpdateItem,
  selectedId,
  onFlip,
  coverImageUrl,
  coverSel,
  onSelectCover,
  onSelectCoverTitle,
  onSelectCoverItem,
  onUpdateCoverTitle,
  onUpdateCoverItem,
}) {
  const blank = (
    <div className={`w-full ${orientation === "landscape" ? "aspect-[1.414/1]" : "aspect-[1/1.414]"} bg-[color:var(--paper)]`} />
  );
  const pages = [
    <CoverFrontPage
      key="cover-front"
      template={template}
      title={album.title}
      orientation={orientation}
      coverImageUrl={coverImageUrl}
      cover={album.cover || {}}
      editable
      onSelectCover={onSelectCover}
      onSelectTitle={onSelectCoverTitle}
      onSelectItem={onSelectCoverItem}
      onUpdateTitle={onUpdateCoverTitle}
      onUpdateItem={onUpdateCoverItem}
      titleSelected={coverSel?.mode === "title"}
      selectedItemId={coverSel?.mode === "item" ? coverSel.itemId : null}
    />,
    <React.Fragment key="blank-inner-front">{blank}</React.Fragment>,
    ...(album.pages || []).map((page, i) => (
      <AlbumPage
        key={page.id || i}
        page={page}
        orientation={orientation}
        pageIndex={i}
        editable
        selectedItemId={selectedId}
        onSelectItem={(item) => onSelectItem(i, item)}
        onUpdateItem={(itemId, patch) => onUpdateItem(i, itemId, patch)}
      />
    )),
    <React.Fragment key="blank-inner-back">{blank}</React.Fragment>,
    <CoverBackPage
      key="cover-back"
      template={template}
      country={album.country}
      year={album.year}
      orientation={orientation}
      cover={album.cover || {}}
    />,
  ];
  return <Flipbook ref={bookRef} pages={pages} orientation={orientation} onFlip={onFlip} />;
}

// ---------- Text Editor ----------
function TextEditor({ item, onChange, onRemove }) {
  return (
    <div className="space-y-4">
      <div>
        <label className="eyebrow block mb-2">Texte</label>
        <textarea
          value={item.content || ""}
          onChange={(e) => onChange({ content: e.target.value })}
          rows={2}
          className="w-full border border-[color:var(--ink)]/20 p-2 text-sm font-sans focus:border-[color:var(--ink)] focus:outline-none"
        />
      </div>
      <div>
        <label className="eyebrow block mb-2">Police</label>
        <select
          data-testid={TID.editorFontSelect}
          value={item.font || FONT_OPTIONS[0].value}
          onChange={(e) => onChange({ font: e.target.value })}
          className="w-full border border-[color:var(--ink)]/20 p-2 text-sm focus:border-[color:var(--ink)] focus:outline-none bg-white"
        >
          {FONT_OPTIONS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="eyebrow block mb-2">Couleur</label>
        <div className="flex items-center gap-2 flex-wrap">
          {COLOR_SWATCHES.map((c) => (
            <button
              key={c}
              onClick={() => onChange({ color: c })}
              className={`w-6 h-6 border ${item.color === c ? "ring-2 ring-[color:var(--coral)] ring-offset-2" : "border-[color:var(--ink)]/20"}`}
              style={{ background: c }}
              aria-label={c}
            />
          ))}
          <input
            data-testid={TID.editorColorInput}
            type="color"
            value={item.color || "#1A1A17"}
            onChange={(e) => onChange({ color: e.target.value })}
            className="w-6 h-6 cursor-pointer bg-transparent border-0 p-0"
          />
        </div>
      </div>
      <div>
        <label className="eyebrow block mb-2">Style</label>
        <div className="flex items-center gap-2">
          <button
            data-testid="editor-text-bold"
            onClick={() => onChange({ font_weight: (item.font_weight === "bold" || item.font_weight === "700") ? "normal" : "bold" })}
            className={`inline-flex items-center justify-center w-9 h-9 border transition-colors ${
              item.font_weight === "bold" || item.font_weight === "700"
                ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
                : "border-[color:var(--ink)]/30 hover:border-[color:var(--ink)]"
            }`}
            title="Gras"
          >
            <Bold size={14} />
          </button>
          <button
            data-testid="editor-text-italic"
            onClick={() => onChange({ font_style: item.font_style === "italic" ? "normal" : "italic" })}
            className={`inline-flex items-center justify-center w-9 h-9 border transition-colors ${
              item.font_style === "italic"
                ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
                : "border-[color:var(--ink)]/30 hover:border-[color:var(--ink)]"
            }`}
            title="Italique"
          >
            <Italic size={14} />
          </button>
        </div>
      </div>
      <div>
        <label className="eyebrow block mb-2">Taille · {item.font_size || 16}px</label>
        <input
          data-testid={TID.editorSizeInput}
          type="range"
          min={10}
          max={72}
          value={item.font_size || 16}
          onChange={(e) => onChange({ font_size: Number(e.target.value) })}
          className="w-full"
        />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <label className="text-xs text-[color:var(--muted)]">
          X %
          <input
            type="number"
            min={0}
            max={100}
            value={Math.round((item.x || 0) * 100)}
            onChange={(e) => onChange({ x: Number(e.target.value) / 100 })}
            className="w-full mt-1 border border-[color:var(--ink)]/20 p-1 text-sm"
          />
        </label>
        <label className="text-xs text-[color:var(--muted)]">
          Y %
          <input
            type="number"
            min={0}
            max={100}
            value={Math.round((item.y || 0) * 100)}
            onChange={(e) => onChange({ y: Number(e.target.value) / 100 })}
            className="w-full mt-1 border border-[color:var(--ink)]/20 p-1 text-sm"
          />
        </label>
      </div>
      <button
        onClick={onRemove}
        className="w-full inline-flex items-center justify-center gap-2 border border-red-300 text-red-600 py-2 hover:bg-red-50 transition-colors"
      >
        <Trash2 size={14} />
        <span className="text-xs font-semibold tracking-widest uppercase">Supprimer</span>
      </button>
    </div>
  );
}

function PhotoEditor({ item, onChange, onRemove }) {
  return (
    <div className="space-y-4">
      <p className="text-xs text-[color:var(--muted)]">Photo sélectionnée. Ajustez le zoom et le cadrage.</p>
      <div>
        <label className="eyebrow block mb-2 flex items-center gap-2"><ZoomIn size={12}/> Zoom · {(item.scale || 1).toFixed(2)}×</label>
        <input
          data-testid="editor-photo-scale"
          type="range"
          min={1}
          max={3}
          step={0.05}
          value={item.scale || 1}
          onChange={(e) => onChange({ scale: Number(e.target.value) })}
          className="w-full"
        />
      </div>
      <div>
        <label className="eyebrow block mb-2 flex items-center gap-2"><Move size={12}/> Cadrage horizontal · {Math.round((item.focal_x ?? 0.5) * 100)}%</label>
        <input
          data-testid="editor-photo-focalx"
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={item.focal_x ?? 0.5}
          onChange={(e) => onChange({ focal_x: Number(e.target.value) })}
          className="w-full"
        />
      </div>
      <div>
        <label className="eyebrow block mb-2 flex items-center gap-2"><Move size={12}/> Cadrage vertical · {Math.round((item.focal_y ?? 0.5) * 100)}%</label>
        <input
          data-testid="editor-photo-focaly"
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={item.focal_y ?? 0.5}
          onChange={(e) => onChange({ focal_y: Number(e.target.value) })}
          className="w-full"
        />
      </div>
      <button
        onClick={() => onChange({ scale: 1, focal_x: 0.5, focal_y: 0.5 })}
        className="w-full text-xs text-[color:var(--muted)] hover:text-[color:var(--ink)] underline underline-offset-4"
        data-testid="editor-photo-reset"
      >
        Réinitialiser le cadrage
      </button>
      <button
        onClick={onRemove}
        className="w-full inline-flex items-center justify-center gap-2 border border-red-300 text-red-600 py-2 hover:bg-red-50 transition-colors"
      >
        <Trash2 size={14} />
        <span className="text-xs font-semibold tracking-widest uppercase">Retirer de la page</span>
      </button>
    </div>
  );
}

// ---------- Cover Editor Panel ----------
function CoverEditorPanel({ album, coverSel, updateCover, updateCoverItem, addCoverText, addCoverShape, removeCoverItem, onDismiss }) {
  const cover = album.cover || {};
  const extras = cover.extra_items || [];
  const selectedItem = coverSel.mode === "item" ? extras.find((it) => it.id === coverSel.itemId) : null;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="eyebrow text-[color:var(--coral)]">Couverture</div>
        <button
          onClick={onDismiss}
          className="text-[color:var(--muted)] hover:text-[color:var(--ink)]"
          data-testid="cover-editor-dismiss"
          aria-label="Fermer"
        >
          <XIcon size={14} />
        </button>
      </div>

      {/* Global cover colors — always visible */}
      <div className="space-y-3">
        <ColorField
          label="Couleur de fond"
          value={cover.bg_color || ""}
          onChange={(v) => updateCover({ bg_color: v || null })}
          tid="cover-bg-color"
          onReset={() => updateCover({ bg_color: null })}
        />
        <ColorField
          label="Couleur d'accent"
          value={cover.accent_color || ""}
          onChange={(v) => updateCover({ accent_color: v || null })}
          tid="cover-accent-color"
          onReset={() => updateCover({ accent_color: null })}
        />
        <ColorField
          label="Couleur du texte"
          value={cover.text_color || ""}
          onChange={(v) => updateCover({ text_color: v || null })}
          tid="cover-text-color"
          onReset={() => updateCover({ text_color: null })}
        />
      </div>

      {/* Title-specific controls */}
      {coverSel.mode === "title" && (
        <div className="border-t border-[color:var(--border-soft)] pt-4 space-y-3">
          <div className="eyebrow">Titre</div>
          <div>
            <label className="eyebrow block mb-2">Police</label>
            <select
              data-testid="cover-title-font"
              value={cover.title_font || "'Cormorant Garamond', serif"}
              onChange={(e) => updateCover({ title_font: e.target.value })}
              className="w-full border border-[color:var(--ink)]/20 p-2 text-sm bg-white"
            >
              <option value="'Cormorant Garamond', serif">Cormorant (serif)</option>
              <option value="'Manrope', sans-serif">Manrope (sans)</option>
              <option value="Georgia, serif">Georgia</option>
              <option value="Helvetica, Arial, sans-serif">Helvetica</option>
              <option value="'Courier New', monospace">Courier</option>
            </select>
          </div>
          <div>
            <label className="eyebrow block mb-2">Taille du titre</label>
            <input
              type="range"
              min={20}
              max={120}
              value={cover.title_font_size || 48}
              onChange={(e) => updateCover({ title_font_size: Number(e.target.value) })}
              className="w-full"
              data-testid="cover-title-size"
            />
          </div>
          <button
            data-testid="cover-title-bold"
            onClick={() => updateCover({ title_font_weight: (cover.title_font_weight === "bold" || cover.title_font_weight === "700") ? "400" : "bold" })}
            className={`inline-flex items-center justify-center w-9 h-9 border transition-colors ${
              cover.title_font_weight === "bold" || cover.title_font_weight === "700" || cover.title_font_weight === "600"
                ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
                : "border-[color:var(--ink)]/30 hover:border-[color:var(--ink)]"
            }`}
            title="Gras"
          >
            <Bold size={14} />
          </button>
        </div>
      )}

      {/* Individual extra-item controls */}
      {selectedItem && (
        <div className="border-t border-[color:var(--border-soft)] pt-4 space-y-3">
          <div className="eyebrow">Élément sélectionné</div>
          {selectedItem.type === "text" && (
            <>
              <textarea
                data-testid="cover-item-content"
                value={selectedItem.content || ""}
                onChange={(e) => updateCoverItem(selectedItem.id, { content: e.target.value })}
                rows={2}
                className="w-full border border-[color:var(--ink)]/20 p-2 text-sm"
              />
              <div className="flex items-center gap-2">
                <button
                  data-testid="cover-item-bold"
                  onClick={() => updateCoverItem(selectedItem.id, { font_weight: selectedItem.font_weight === "bold" ? "normal" : "bold" })}
                  className={`inline-flex items-center justify-center w-9 h-9 border ${
                    selectedItem.font_weight === "bold" ? "bg-[color:var(--ink)] text-[color:var(--paper)]" : "border-[color:var(--ink)]/30"
                  }`}
                >
                  <Bold size={14} />
                </button>
                <input
                  type="range"
                  min={10}
                  max={72}
                  value={selectedItem.font_size || 22}
                  onChange={(e) => updateCoverItem(selectedItem.id, { font_size: Number(e.target.value) })}
                  className="flex-1"
                  data-testid="cover-item-size"
                />
                <span className="text-xs w-8 text-right">{selectedItem.font_size || 22}px</span>
              </div>
              <input
                type="color"
                data-testid="cover-item-color"
                value={selectedItem.color || "#F9F8F6"}
                onChange={(e) => updateCoverItem(selectedItem.id, { color: e.target.value })}
                className="w-full h-9 border border-[color:var(--ink)]/20 cursor-pointer"
              />
            </>
          )}
          {selectedItem.type === "shape" && (
            <input
              type="color"
              data-testid="cover-item-fill"
              value={selectedItem.fill_color || "#E56B55"}
              onChange={(e) => updateCoverItem(selectedItem.id, { fill_color: e.target.value })}
              className="w-full h-9 border border-[color:var(--ink)]/20 cursor-pointer"
            />
          )}
          <button
            onClick={() => removeCoverItem(selectedItem.id)}
            className="w-full inline-flex items-center justify-center gap-2 border border-red-300 text-red-600 py-2 hover:bg-red-50 transition-colors"
            data-testid="cover-item-remove"
          >
            <Trash2 size={14} />
            <span className="text-xs font-semibold tracking-widest uppercase">Retirer</span>
          </button>
        </div>
      )}

      {/* Add elements */}
      <div className="border-t border-[color:var(--border-soft)] pt-4 space-y-2">
        <div className="eyebrow">Ajouter</div>
        <button
          data-testid="cover-add-text"
          onClick={() => addCoverText()}
          className="w-full inline-flex items-center justify-center gap-2 border border-[color:var(--ink)]/30 py-2 hover:border-[color:var(--ink)]"
        >
          <Type size={14} />
          <span className="text-xs font-semibold tracking-widest uppercase">Texte</span>
        </button>
        <div className="grid grid-cols-2 gap-2">
          <button
            data-testid="cover-add-rect"
            onClick={() => addCoverShape("rect")}
            className="inline-flex items-center justify-center gap-2 border border-[color:var(--ink)]/30 py-2 hover:border-[color:var(--ink)]"
          >
            <Square size={14} />
            <span className="text-xs font-semibold tracking-widest uppercase">Rect</span>
          </button>
          <button
            data-testid="cover-add-circle"
            onClick={() => addCoverShape("circle")}
            className="inline-flex items-center justify-center gap-2 border border-[color:var(--ink)]/30 py-2 hover:border-[color:var(--ink)]"
          >
            <CircleIcon size={14} />
            <span className="text-xs font-semibold tracking-widest uppercase">Cercle</span>
          </button>
        </div>
        <div className="flex items-center gap-2 text-xs text-[color:var(--muted)] pt-1">
          <ClipboardPaste size={12} />
          <span>Ctrl+V pour coller du texte comme élément</span>
        </div>
      </div>
    </div>
  );
}

function ColorField({ label, value, onChange, tid, onReset }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className="eyebrow">{label}</label>
        <button onClick={onReset} className="text-[10px] text-[color:var(--muted)] hover:text-[color:var(--ink)] underline">
          template
        </button>
      </div>
      <div className="flex items-center gap-2">
        <input
          data-testid={tid}
          type="color"
          value={value || "#000000"}
          onChange={(e) => onChange(e.target.value)}
          className="w-9 h-9 border border-[color:var(--ink)]/20 cursor-pointer p-0"
        />
        <input
          type="text"
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder="par défaut"
          className="flex-1 border border-[color:var(--ink)]/20 px-2 py-1 text-xs font-mono"
        />
      </div>
    </div>
  );
}

// ---------- Processing screen ----------
function ProcessingScreen({ title }) {
  const [dots, setDots] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setDots((d) => (d + 1) % 4), 500);
    return () => clearInterval(t);
  }, []);
  const stages = [
    "Analyse des images…",
    "Détection des doublons…",
    "Regroupement par scène…",
    "Composition des pages…",
  ];
  const [stage, setStage] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setStage((s) => (s + 1) % stages.length), 2000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <main className="min-h-screen bg-[color:var(--paper)] flex items-center justify-center pt-20 relative">
      <div className="absolute inset-0 grain pointer-events-none" />
      <div className="text-center max-w-lg px-6 relative">
        <Sparkles size={32} className="mx-auto text-[color:var(--coral)] mb-8 animate-slow-pulse" />
        <div className="eyebrow mb-4">L'IA compose votre édition</div>
        <h1 className="font-serif-display text-5xl md:text-6xl leading-[1] tracking-tight mb-8">
          {title}
        </h1>
        <p className="font-serif-display text-xl md:text-2xl text-[color:var(--muted)] italic">
          {stages[stage]}{".".repeat(dots)}
        </p>
      </div>
    </main>
  );
}

function cryptoRandom() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `id-${Math.random().toString(36).slice(2, 10)}`;
}
