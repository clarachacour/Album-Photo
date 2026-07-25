import React, { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { api, pdfExportUrl, coverImageUrl, coverAssetUrl } from "@/lib/api";
import { toast } from "sonner";
import { getTemplate, COVER_COLOR_PRESETS } from "@/lib/coverTemplates";
import { CoverEditorPanel } from "@/components/CoverEditorPanel";
import { CoverSpine } from "@/components/CoverSpine";
import { makeCoverEditingActions } from "@/lib/coverEditing";
import { AlbumPage, CoverFrontPage, CoverBackPage } from "@/components/AlbumPage";
import Flipbook from "@/components/Flipbook";
import PhotoTray from "@/components/PhotoTray";
import { TID } from "@/constants/testIds";
import { ChevronLeft, ChevronRight, Download, Save, Sparkles, Type, Trash2, Loader2, ArrowLeft, Image as ImageIcon, X as XIcon, ZoomIn, Move, Bold, Italic, Square, Circle as CircleIcon, ClipboardPaste } from "lucide-react";

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
  
  const isCreating = !id || id === "new";

  // --- États du Formulaire de Création ---
  const [templateId, setTemplateId] = useState(COVER_COLOR_PRESETS?.[0]?.id || "default");
  const [size, setSize] = useState("A4");
  const [orientation, setOrientation] = useState("portrait");
  const [title, setTitle] = useState("");
  const [country, setCountry] = useState("");
  const [year, setYear] = useState(new Date().getFullYear());
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef();

  // --- États de l'Éditeur ---
  const bookRef = useRef();
  const coverInputRef = useRef();
  const [album, setAlbum] = useState(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [selected, setSelected] = useState(null);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [uploadingCover, setUploadingCover] = useState(false);
  const [coverVersion, setCoverVersion] = useState(0);
  const [processing, setProcessing] = useState(params.get("processing") === "1");
  const [coverSel, setCoverSel] = useState(null);

  const loadAlbum = useCallback(async () => {
    if (isCreating) return;
    try {
      const { data } = await api.get(`/albums/${id}`);
      setAlbum(data);
      if (data.status === "processing") setProcessing(true);
      else setProcessing(false);
    } catch {
      toast.error("Impossible de charger cet album");
      nav("/dashboard");
    }
  }, [id, isCreating, nav]);

  useEffect(() => {
    if (!isCreating) {
      loadAlbum();
    }
  }, [loadAlbum, isCreating]);

  useEffect(() => {
    if (isCreating || !coverSel) return;
    const onPaste = (e) => {
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
  }, [coverSel, isCreating]);

  useEffect(() => {
    if (!processing || isCreating) return;
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
  }, [processing, id, loadAlbum, isCreating]);

  const template = isCreating
    ? getTemplate()
    : (album ? getTemplate() : null);

  const handleFiles = (list) => {
    const arr = Array.from(list).filter((f) => f.type.startsWith("image/"));
    setFiles((prev) => [...prev, ...arr]);
  };

  const removeFile = (idx) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const createAndProcess = async () => {
    if (!title.trim()) {
      toast.error("Veuillez entrer un titre pour l'album");
      return;
    }
    if (files.length === 0) {
      toast.error("Veuillez ajouter au moins une photo");
      return;
    }

    setBusy(true);
    try {
      const { data: newAlbum } = await api.post("/albums", {
        title: title.trim(),
        country: country.trim(),
        year: Number(year) || new Date().getFullYear(),
        size,
        orientation,
      });

      const chunkSize = 8;
      for (let i = 0; i < files.length; i += chunkSize) {
        const chunk = files.slice(i, i + chunkSize);
        const form = new FormData();
        chunk.forEach((f) => form.append("files", f));
        await api.post(`/albums/${newAlbum.id}/photos`, form, {
          headers: { "Content-Type": "multipart/form-data" },
        });
      }

      await api.post(`/albums/${newAlbum.id}/process`);
      toast.success("L'IA compose votre album...");
      nav(`/editor/${newAlbum.id}?processing=1`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Erreur lors de la création");
      setBusy(false);
    }
  };

  const save = async () => {
    if (!album) return;
    setSaving(true);
    try {
      await api.patch(`/albums/${id}`, { title: album.title, country: album.country, year: album.year, pages: album.pages, cover: album.cover || {} });
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

  const { updateCover, updateAlbumTitle, updateCoverItem, addCoverText, addCoverShape, addCoverImage, removeCoverItem } =
    makeCoverEditingActions({ setAlbum, albumId: id, coverSel, setCoverSel });

  const addTextToCurrentPage = () => {
    if (!album || !album.pages || album.pages.length === 0) return;
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

  const photoSequence = () => {
    const seq = [];
    for (const p of album?.pages || []) {
      for (const it of p.items || []) {
        if (it.type === "photo") seq.push(it.photo_id);
      }
    }
    return seq;
  };

  // ==========================================
  // RENDU : CRÉATION D'ALBUM (SANS STEPS)
  // ==========================================
  if (isCreating) {
    return (
      <main className="min-h-screen bg-[color:var(--paper)] pt-12 pb-24 px-6 md:px-12">
        <div className="max-w-[1000px] mx-auto">
         
          <div className="mb-10">
            <h1 className="font-serif-display text-4xl mb-2">Créer un nouvel album</h1>
            <p className="text-sm text-[color:var(--muted)]">Remplissez les informations et ajoutez vos photos pour lancer la composition automatique.</p>
          </div>

          <div className="space-y-10 bg-white p-8 border border-[color:var(--border-soft)]">
            {/* 1. Informations générales */}
            <div className="space-y-4">
              <h2 className="font-serif-display text-xl border-b border-[color:var(--border-soft)] pb-2">Informations</h2>
              <div>
                <label className="eyebrow block mb-2">Titre de l'album *</label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="ex: Voyage en Italie"
                  className="w-full border border-[color:var(--ink)]/20 p-3 text-base bg-white focus:outline-none focus:border-[color:var(--ink)]"
                />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="eyebrow block mb-2">Lieu / Pays</label>
                  <input
                    type="text"
                    value={country}
                    onChange={(e) => setCountry(e.target.value)}
                    placeholder="ex: Toscane"
                    className="w-full border border-[color:var(--ink)]/20 p-3 text-base bg-white focus:outline-none focus:border-[color:var(--ink)]"
                  />
                </div>
                <div>
                  <label className="eyebrow block mb-2">Année</label>
                  <input
                    type="number"
                    value={year}
                    onChange={(e) => setYear(e.target.value)}
                    className="w-full border border-[color:var(--ink)]/20 p-3 text-base bg-white focus:outline-none focus:border-[color:var(--ink)]"
                  />
                </div>
              </div>
            </div>

            {/* 2. Format et Style de couverture */}
            <div className="space-y-4">
              <h2 className="font-serif-display text-xl border-b border-[color:var(--border-soft)] pb-2">Mise en page & Couverture</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="eyebrow block mb-2">Format</label>
                  <div className="grid grid-cols-3 gap-2">
                    {["A4", "A5", "Square"].map((s) => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => setSize(s)}
                        className={`py-3 border text-xs font-semibold uppercase tracking-wider transition-all ${
                          size === s ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]" : "bg-white border-[color:var(--border-soft)] hover:border-[color:var(--ink)]"
                        }`}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="eyebrow block mb-2">Orientation</label>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { id: "portrait", label: "Portrait" },
                      { id: "landscape", label: "Paysage" },
                    ].map((o) => (
                      <button
                        key={o.id}
                        type="button"
                        onClick={() => setOrientation(o.id)}
                        className={`py-3 border text-xs font-semibold uppercase tracking-wider transition-all ${
                          orientation === o.id ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]" : "bg-white border-[color:var(--border-soft)] hover:border-[color:var(--ink)]"
                        }`}
                      >
                        {o.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div>
                <label className="eyebrow block mb-2">Style de couverture</label>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {COVER_COLOR_PRESETS.map((t) => (
                    <div
                      key={t.id}
                      onClick={() => setTemplateId(t.id)}
                      className={`cursor-pointer p-4 border transition-all bg-white flex flex-col justify-between ${
                        templateId === t.id ? "border-[color:var(--coral)] ring-1 ring-[color:var(--coral)]" : "border-[color:var(--border-soft)] hover:border-[color:var(--ink)]/30"
                      }`}
                    >
                      <div>
                        <h3 className="font-serif-display text-lg mb-1">{t.name}</h3>
                        <p className="text-xs text-[color:var(--muted)]">{t.description}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* 3. Photos */}
            <div className="space-y-4">
              <h2 className="font-serif-display text-xl border-b border-[color:var(--border-soft)] pb-2">Photos</h2>
              <div
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  if (e.dataTransfer.files) handleFiles(e.dataTransfer.files);
                }}
                className="border-2 border-dashed border-[color:var(--ink)]/30 bg-[color:var(--paper)] p-8 text-center cursor-pointer hover:border-[color:var(--coral)] transition-colors"
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files) handleFiles(e.target.files);
                    e.target.value = "";
                  }}
                />
                <ImageIcon size={32} className="mx-auto text-[color:var(--muted)] mb-3" />
                <p className="text-sm font-semibold mb-1">Click or drag your photos here</p>
                <p className="text-xs text-[color:var(--muted)]">JPEG, PNG, WEBP accepted</p>
              </div>

              {files.length > 0 && (
                <div>
                  <div className="eyebrow mb-2">{files.length} photo(s) sélectionnée(s)</div>
                  <div className="grid grid-cols-3 sm:grid-cols-6 gap-3 max-h-48 overflow-y-auto p-2 border border-[color:var(--border-soft)] bg-gray-50">
                    {files.map((file, idx) => (
                      <div key={idx} className="relative group aspect-square bg-gray-200 border overflow-hidden">
                        <img
                          src={URL.createObjectURL(file)}
                          alt={`upload-${idx}`}
                          className="w-full h-full object-cover"
                        />
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            removeFile(idx);
                          }}
                          className="absolute top-1 right-1 bg-black/60 text-white p-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          <XIcon size={12} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Bouton de validation final */}
            <div className="pt-4 border-t border-[color:var(--border-soft)] flex justify-end">
              <button
                onClick={createAndProcess}
                disabled={busy}
                className="inline-flex items-center gap-3 bg-[color:var(--coral)] text-[color:var(--paper)] px-8 py-4 hover:bg-[color:var(--ink)] transition-colors disabled:opacity-60"
              >
                {busy ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
                <span className="text-sm font-semibold tracking-widest uppercase">Lancer la création par l'IA</span>
              </button>
            </div>
          </div>
        </div>
      </main>
    );
  }

  // ==========================================
  // RENDU : ÉCRAN DE CHARGEMENT DE L'IA
  // ==========================================
  if (!album) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[color:var(--editor-canvas)]">
        <p className="eyebrow animate-slow-pulse">Loading memories...</p>
      </div>
    );
  }

  if (processing) {
    return <ProcessingScreen title={album.title} />;
  }

  // ==========================================
  // RENDU : ÉDITEUR D'ALBUM PRINCIPAL
  // ==========================================
  const albumOrientation = album?.orientation || "portrait";
  const albumTemplate = getTemplate();

  return (
    <main className="min-h-screen bg-[color:var(--editor-canvas)] pt-20 pb-24 relative">
      <div className="absolute inset-0 grain pointer-events-none" />

      <div className="max-w-[1600px] mx-auto px-4 md:px-8 grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6 items-start">
        {/* Zone du Livre */}
        <div className="flex flex-col items-center pt-6">
          <div className="w-full max-w-2xl mb-8 flex items-center justify-between">
            <h1 className="font-serif-display text-2xl truncate">{album.title}</h1>
            <div />
          </div>

          <BookRenderer
            album={album}
            template={albumTemplate}
            orientation={albumOrientation}
            bookRef={bookRef}
            onSelectItem={(pageIdx, item) => {
              setSelected({ pageIdx, item });
              setCoverSel(null);
            }}
            onUpdateItem={updateItemById}
            selectedId={selected?.item?.id}
            onFlip={(p) => {
              setPageIndex(p);
              if (p !== 0) setCoverSel(null);
            }}
            coverImageUrl={album.cover_image_path ? coverImageUrl(id, coverVersion) : null}
            coverSel={coverSel}
            onSelectCover={(side = "front") => { setSelected(null); setCoverSel({ mode: "cover", side }); }}
            onSelectCoverTitle={() => { setSelected(null); setCoverSel({ mode: "title", side: "front" }); }}
            onSelectCoverItem={(item, side = "front") => { setSelected(null); setCoverSel({ mode: "item", side, itemId: item.id }); }}
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

        {/* Barre latérale (Sidebar) */}
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
                addCoverImage={addCoverImage}
                removeCoverItem={removeCoverItem}
                updateAlbumTitle={updateAlbumTitle}
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
                Cliquez sur un élément pour l'éditer. Sur la couverture, cliquez sur le fond, le titre ou un élément ajouté.<br /><br />
                <em>Astuce</em> : déplacez et redimensionnez chaque élément directement dans le livre.
              </p>
            )}
          </div>

          <div className="border-t border-[color:var(--border-soft)] pt-6 mt-6">
            <div className="eyebrow mb-3">À propos</div>
            <div className="text-sm text-[color:var(--ink)]/70 space-y-1">
              <div>{album.pages?.length || 0} pages</div>
              <div>{album.photos?.filter((p) => p.is_selected).length || 0} photos utilisées</div>
              <div>Format : {album.size} · {albumOrientation}</div>
            </div>
          </div>
        </aside>
      </div>
    </main>
  );
}

// ==========================================
// SOUS-COMPOSANTS DE L'ÉDITEUR
// ==========================================

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
      onSelectCover={() => onSelectCover("front")}
      onSelectTitle={onSelectCoverTitle}
      onSelectItem={(item) => onSelectCoverItem(item, "front")}
      onUpdateTitle={onUpdateCoverTitle}
      onUpdateItem={(itemId, patch) => onUpdateCoverItem(itemId, patch, "front")}
      titleSelected={coverSel?.mode === "title"}
      selectedItemId={coverSel?.mode === "item" && coverSel?.side === "front" ? coverSel.itemId : null}
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
      editable
      onSelectCover={() => onSelectCover("back")}
      onSelectItem={(item) => onSelectCoverItem(item, "back")}
      onUpdateItem={(itemId, patch) => onUpdateCoverItem(itemId, patch, "back")}
      selectedItemId={coverSel?.mode === "item" && coverSel?.side === "back" ? coverSel.itemId : null}
    />,
  ];
  return <Flipbook ref={bookRef} pages={pages} orientation={orientation} onFlip={onFlip} />;
}

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

function ProcessingScreen({ title }) {
  const [dots, setDots] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setDots((d) => (d + 1) % 4), 500);
    return () => clearInterval(t);
  }, []);
  const stages = [
    "Analysing images…",
    "Detecting duplicates…",
    "Grouping by scene…",
    "Composing pages…",
  ];
  const [stage, setStage] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setStage((s) => (s + 1) % stages.length), 2000);
    return () => clearInterval(t);
  }, []);
  return (
    <main className="min-h-screen bg-[color:var(--paper)] flex items-center justify-center pt-20 relative">
      <div className="absolute inset-0 grain pointer-events-none" />
      <div className="text-center max-w-lg px-6 relative">
        <Sparkles size={32} className="mx-auto text-[color:var(--coral)] mb-8 animate-slow-pulse" />
        <div className="eyebrow mb-4">The AI is composing your edit</div>
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