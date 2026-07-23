import React, { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { api, pdfExportUrl, coverImageUrl, photoImageUrl } from "@/lib/api";
import { toast } from "sonner";
import { getTemplate } from "@/lib/coverTemplates";
import { AlbumPage, CoverFrontPage, CoverBackPage } from "@/components/AlbumPage";
import Flipbook from "@/components/Flipbook";
import PhotoTray from "@/components/PhotoTray";
import { TID } from "@/constants/testIds";
import { ChevronLeft, ChevronRight, Download, Save, Sparkles, Type, Trash2, Loader2, ArrowLeft, Image as ImageIcon, X as XIcon, ZoomIn, Move } from "lucide-react";

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
      await api.patch(`/albums/${id}`, { pages: album.pages });
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
            onSelect={(pageIdx, item) => setSelected({ pageIdx, item })}
            selectedId={selected?.item?.id}
            onFlip={(p) => setPageIndex(p)}
            coverImageUrl={album.cover_image_path ? coverImageUrl(id, coverVersion) : null}
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
            {selected ? (
              selected.item.type === "text" ? (
                <TextEditor item={selected.item} onChange={updateSelectedItem} onRemove={removeSelected} />
              ) : (
                <PhotoEditor item={selected.item} onChange={updateSelectedItem} onRemove={removeSelected} />
              )
            ) : (
              <p className="text-xs text-[color:var(--muted)] leading-relaxed">
                Cliquez sur un texte ou une photo pour l'éditer.<br /><br />
                Astuce : le bouton <em>Ajouter texte</em> place une légende sur la page visible.
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
function BookRenderer({ album, template, orientation, bookRef, onSelect, selectedId, onFlip, coverImageUrl }) {
  const blank = (
    <div className={`w-full ${orientation === "landscape" ? "aspect-[1.414/1]" : "aspect-[1/1.414]"} bg-[color:var(--paper)]`} />
  );
  const pages = [
    <CoverFrontPage key="cover-front" template={template} title={album.title} orientation={orientation} coverImageUrl={coverImageUrl} />,
    <React.Fragment key="blank-inner-front">{blank}</React.Fragment>,
    ...(album.pages || []).map((page, i) => (
      <AlbumPage
        key={page.id || i}
        page={page}
        template={template}
        orientation={orientation}
        pageIndex={i}
        editable
        selectedItemId={selectedId}
        onSelectItem={(item) => onSelect(i, item)}
      />
    )),
    <React.Fragment key="blank-inner-back">{blank}</React.Fragment>,
    <CoverBackPage key="cover-back" template={template} country={album.country} year={album.year} orientation={orientation} />,
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
