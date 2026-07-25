import React, { useState, useEffect, useRef } from "react";
import { Rnd } from "react-rnd";
import {
  Sparkles,
  Bold,
  Italic,
  Trash2,
  ZoomIn,
  Move,
  ChevronLeft,
  ChevronRight,
  Type,
} from "lucide-react";

// --- CONSTANTES & CONFIGURATION ---

const FONT_OPTIONS = [
  { value: "sans", label: "Sans-serif (Moderne)" },
  { value: "serif", label: "Serif (Classique)" },
  { value: "mono", label: "Monospace (Épuré)" },
];

const COLOR_SWATCHES = [
  "#1A1A17", // Ink
  "#FBF9F5", // Paper
  "#E07A5F", // Coral
  "#3D405B", // Navy
  "#81B29A", // Sage
  "#F2CC8F", // Sand
];

const TID = {
  editorFontSelect: "editor-font-select",
  editorColorInput: "editor-color-input",
  editorSizeInput: "editor-size-input",
};

const PROCESSING_STAGES = [
  "Analysing images…",
  "Detecting duplicates…",
  "Grouping by scene…",
  "Composing pages…",
];

// --- UTILITAIRES ---

function cryptoRandom() {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
  } catch (e) {
    // Restitution en cas d'environnement non sécurisé (HTTP)
  }
  return `id-${Math.random().toString(36).slice(2, 10)}-${Date.now()}`;
}

// --- COMPOSANT PRINCIPAL ---

export default function AlbumEditor({ album, onSave, onBack }) {
  const [currentPageIndex, setCurrentPageIndex] = useState(0);
  const [selectedItemId, setSelectedItemId] = useState(null);
  const [pages, setPages] = useState(album?.pages || []);
  const [isProcessing, setIsProcessing] = useState(false);

  // États et Ref pour le centrage et le snap
  const [snapLines, setSnapLines] = useState({ x: null, y: null });
  const containerRef = useRef(null);

  const currentPage = pages[currentPageIndex] || { items: [] };
  const selectedItem = currentPage.items?.find((item) => item.id === selectedItemId);

  // 1. GESTION DE LA TOUCHE SUPPR / BACKSPACE DU CLAVIER
  useEffect(() => {
    const handleKeyDown = (event) => {
      if (!selectedItemId) return;

      const activeEl = document.activeElement;
      const isEditingText =
        activeEl.tagName === "INPUT" ||
        activeEl.tagName === "TEXTAREA" ||
        activeEl.isContentEditable;

      if (isEditingText) return;

      if (event.key === "Delete" || event.key === "Backspace") {
        event.preventDefault();
        handleRemoveItem();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedItemId]);

  // 2. DETECTION DU CENTRAGE (SNAP GUIDES)
  const checkSnapGuides = (x, y, width = 0, height = 0) => {
    if (!containerRef.current) return;

    const rect = containerRef.current.getBoundingClientRect();
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;

    const itemCenterX = x + width / 2;
    const itemCenterY = y + height / 2;

    const THRESHOLD = 6; // Sensibilité en pixels

    setSnapLines({
      x: Math.abs(itemCenterX - centerX) < THRESHOLD ? centerX : null,
      y: Math.abs(itemCenterY - centerY) < THRESHOLD ? centerY : null,
    });
  };

  // Mettre à jour un élément spécifique sur la page courante
  const handleUpdateItem = (updatedProps) => {
    if (!selectedItemId) return;

    setPages((prevPages) => {
      const newPages = [...prevPages];
      const pageToUpdate = { ...newPages[currentPageIndex] };

      pageToUpdate.items = pageToUpdate.items.map((item) => {
        if (item.id === selectedItemId) {
          return { ...item, ...updatedProps };
        }
        return item;
      });

      newPages[currentPageIndex] = pageToUpdate;
      return newPages;
    });
  };

  // Supprimer l'élément sélectionné
  const handleRemoveItem = () => {
    if (!selectedItemId) return;

    setPages((prevPages) => {
      const newPages = [...prevPages];
      const pageToUpdate = { ...newPages[currentPageIndex] };

      pageToUpdate.items = pageToUpdate.items.filter((item) => item.id !== selectedItemId);
      newPages[currentPageIndex] = pageToUpdate;
      return newPages;
    });

    setSelectedItemId(null);
  };

  // Ajouter un bloc de texte
  const handleAddText = () => {
    const newItem = {
      id: cryptoRandom(),
      type: "text",
      content: "Nouveau texte",
      font: FONT_OPTIONS[0].value,
      color: "#1A1A17",
      font_size: 16,
      font_weight: "normal",
      font_style: "normal",
      x: 20,
      y: 20,
      width: 150,
      height: 50,
    };

    setPages((prevPages) => {
      const newPages = [...prevPages];
      const pageToUpdate = { ...newPages[currentPageIndex] };
      pageToUpdate.items = [...(pageToUpdate.items || []), newItem];
      newPages[currentPageIndex] = pageToUpdate;
      return newPages;
    });

    setSelectedItemId(newItem.id);
  };

  if (isProcessing) {
    return <ProcessingScreen title={album?.title || "Création de l'album"} />;
  }

  return (
    <div className="min-h-screen bg-[color:var(--paper)] text-[color:var(--ink)] flex flex-col">
      {/* Barre d'outils supérieure */}
      <header className="border-b border-[color:var(--ink)]/10 px-6 py-4 flex items-center justify-between bg-white/50 backdrop-blur-sm sticky top-0 z-10">
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-2 text-sm hover:opacity-75 transition-opacity"
          >
            <ChevronLeft size={16} />
            Retour
          </button>
          <h1 className="font-serif-display text-xl font-semibold">{album?.title || "Album"}</h1>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleAddText}
            className="inline-flex items-center gap-2 border border-[color:var(--ink)]/20 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider hover:bg-[color:var(--ink)] hover:text-[color:var(--paper)] transition-colors"
          >
            <Type size={14} />
            Ajouter du texte
          </button>
          <button
            type="button"
            onClick={() => onSave?.(pages)}
            className="inline-flex items-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] px-4 py-1.5 text-xs font-semibold uppercase tracking-wider hover:opacity-90 transition-opacity"
          >
            Sauvegarder
          </button>
        </div>
      </header>

      {/* Zone de travail principale */}
      <div className="flex-1 flex overflow-hidden">
        {/* Navigation des pages */}
        <aside className="w-64 border-r border-[color:var(--ink)]/10 p-4 overflow-y-auto hidden md:block">
          <h2 className="eyebrow mb-4">Pages ({pages.length})</h2>
          <div className="space-y-3">
            {pages.map((page, idx) => (
              <button
                key={page.id || idx}
                type="button"
                onClick={() => {
                  setCurrentPageIndex(idx);
                  setSelectedItemId(null);
                }}
                className={`w-full p-3 border text-left transition-all ${
                  currentPageIndex === idx
                    ? "border-[color:var(--ink)] bg-white shadow-sm"
                    : "border-[color:var(--ink)]/10 hover:border-[color:var(--ink)]/30"
                }`}
              >
                <span className="text-xs font-mono block mb-1">Page {idx + 1}</span>
                <span className="text-xs text-[color:var(--muted)]">
                  {page.items?.length || 0} élément(s)
                </span>
              </button>
            ))}
          </div>
        </aside>

        {/* Zone d'édition centrale */}
        <main
          className="flex-1 p-8 flex flex-col items-center justify-center overflow-y-auto relative"
          onClick={() => setSelectedItemId(null)}
        >
          <div
            ref={containerRef}
            className="relative w-full max-w-2xl aspect-[3/4] bg-white border border-[color:var(--ink)]/10 shadow-lg p-8 overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Ligne Guide Verticale (Axe X) */}
            {snapLines.x !== null && (
              <div
                className="absolute top-0 bottom-0 border-l-2 border-dashed border-red-500 z-50 pointer-events-none"
                style={{ left: `${snapLines.x}px` }}
              />
            )}

            {/* Ligne Guide Horizontale (Axe Y) */}
            {snapLines.y !== null && (
              <div
                className="absolute left-0 right-0 border-t-2 border-dashed border-red-500 z-50 pointer-events-none"
                style={{ top: `${snapLines.y}px` }}
              />
            )}

            {/* Rendu dynamique de TOUS les éléments avec React-Rnd */}
            {currentPage.items?.map((item) => {
              const isSelected = item.id === selectedItemId;

              return (
                <Rnd
                  key={item.id}
                  size={{
                    width: item.width || 150,
                    height: item.height || 50,
                  }}
                  position={{
                    x: item.x || 0,
                    y: item.y || 0,
                  }}
                  onDragStart={(e) => {
                    e.stopPropagation();
                    setSelectedItemId(item.id);
                  }}
                  onDrag={(e, d) =>
                    checkSnapGuides(d.x, d.y, item.width || 150, item.height || 50)
                  }
                  onDragStop={(e, d) => {
                    setSnapLines({ x: null, y: null });
                    // Mise à jour directe par ID
                    setPages((prevPages) => {
                      const newPages = [...prevPages];
                      const pageToUpdate = { ...newPages[currentPageIndex] };
                      pageToUpdate.items = pageToUpdate.items.map((it) =>
                        it.id === item.id ? { ...it, x: d.x, y: d.y } : it
                      );
                      newPages[currentPageIndex] = pageToUpdate;
                      return newPages;
                    });
                  }}
                  onResizeStop={(e, direction, ref, delta, position) => {
                    setSnapLines({ x: null, y: null });
                    setPages((prevPages) => {
                      const newPages = [...prevPages];
                      const pageToUpdate = { ...newPages[currentPageIndex] };
                      pageToUpdate.items = pageToUpdate.items.map((it) =>
                        it.id === item.id
                          ? {
                              ...it,
                              width: parseInt(ref.style.width, 10),
                              height: parseInt(ref.style.height, 10),
                              ...position,
                            }
                          : it
                      );
                      newPages[currentPageIndex] = pageToUpdate;
                      return newPages;
                    });
                  }}
                  bounds="parent"
                  onMouseDown={(e) => {
                    e.stopPropagation();
                    setSelectedItemId(item.id);
                  }}
                  className={`absolute cursor-move ${
                    isSelected ? "ring-2 ring-[color:var(--coral,#f53769)]" : ""
                  }`}
                >
                  {item.type === "photo" ? (
                    <div className="w-full h-full overflow-hidden relative pointer-events-none select-none">
                      <img
                        src={item.url || item.src}
                        alt="Élément d'album"
                        className="w-full h-full object-cover pointer-events-none"
                        style={{
                          transform: `scale(${item.scale || 1})`,
                          objectPosition: `${(item.focal_x ?? 0.5) * 100}% ${
                            (item.focal_y ?? 0.5) * 100
                          }%`,
                        }}
                      />
                    </div>
                  ) : (
                    <div
                      style={{
                        color: item.color || "#1A1A17",
                        fontSize: `${item.font_size || 16}px`,
                        fontWeight: item.font_weight || "normal",
                        fontStyle: item.font_style || "normal",
                        fontFamily: item.font || "sans-serif",
                      }}
                      className="w-full h-full select-none pointer-events-none flex items-center"
                    >
                      {item.content || "Texte vide"}
                    </div>
                  )}
                </Rnd>
              );
            })}
          </div>

          {/* Navigation bas de page mobile */}
          <div className="flex items-center gap-4 mt-6">
            <button
              type="button"
              disabled={currentPageIndex === 0}
              onClick={() => {
                setCurrentPageIndex((p) => Math.max(0, p - 1));
                setSelectedItemId(null);
              }}
              className="p-2 border border-[color:var(--ink)]/20 disabled:opacity-30"
            >
              <ChevronLeft size={18} />
            </button>
            <span className="text-xs font-mono">
              {currentPageIndex + 1} / {pages.length || 1}
            </span>
            <button
              type="button"
              disabled={currentPageIndex >= pages.length - 1}
              onClick={() => {
                setCurrentPageIndex((p) => Math.min(pages.length - 1, p + 1));
                setSelectedItemId(null);
              }}
              className="p-2 border border-[color:var(--ink)]/20 disabled:opacity-30"
            >
              <ChevronRight size={18} />
            </button>
          </div>
        </main>

        {/* Panneau d'inspection latéral */}
        <aside className="w-80 border-l border-[color:var(--ink)]/10 p-6 bg-white/50 backdrop-blur-sm overflow-y-auto">
          <h2 className="eyebrow mb-6">Propriétés</h2>
          {selectedItem ? (
            selectedItem.type === "text" ? (
              <TextEditor
                item={selectedItem}
                onChange={handleUpdateItem}
                onRemove={handleRemoveItem}
              />
            ) : (
              <PhotoEditor
                item={selectedItem}
                onChange={handleUpdateItem}
                onRemove={handleRemoveItem}
              />
            )
          ) : (
            <p className="text-xs text-[color:var(--muted)] italic">
              Sélectionnez un élément sur la page pour modifier ses propriétés.
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}

// --- SOUS-COMPOSANTS ---

function TextEditor({ item, onChange, onRemove }) {
  const isBold =
    item.font_weight === "bold" || item.font_weight === "700" || item.font_weight === 700;
  const isItalic = item.font_style === "italic";

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
              type="button"
              onClick={() => onChange({ color: c })}
              className={`w-6 h-6 border ${
                item.color === c
                  ? "ring-2 ring-[color:var(--coral)] ring-offset-2"
                  : "border-[color:var(--ink)]/20"
              }`}
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
            type="button"
            data-testid="editor-text-bold"
            onClick={() => onChange({ font_weight: isBold ? "normal" : "bold" })}
            className={`inline-flex items-center justify-center w-9 h-9 border transition-colors ${
              isBold
                ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
                : "border-[color:var(--ink)]/30 hover:border-[color:var(--ink)]"
            }`}
            title="Gras"
          >
            <Bold size={14} />
          </button>

          <button
            type="button"
            data-testid="editor-text-italic"
            onClick={() => onChange({ font_style: isItalic ? "normal" : "italic" })}
            className={`inline-flex items-center justify-center w-9 h-9 border transition-colors ${
              isItalic
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
        type="button"
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
  const scale = Number(item.scale ?? 1);
  const focalX = Number(item.focal_x ?? 0.5);
  const focalY = Number(item.focal_y ?? 0.5);

  return (
    <div className="space-y-4">
      <p className="text-xs text-[color:var(--muted)]">
        Photo sélectionnée. Ajustez le zoom et le cadrage.
      </p>

      <div>
        <label className="eyebrow block mb-2 flex items-center gap-2">
          <ZoomIn size={12} /> Zoom · {scale.toFixed(2)}×
        </label>
        <input
          data-testid="editor-photo-scale"
          type="range"
          min={1}
          max={3}
          step={0.05}
          value={scale}
          onChange={(e) => onChange({ scale: Number(e.target.value) })}
          className="w-full"
        />
      </div>

      <div>
        <label className="eyebrow block mb-2 flex items-center gap-2">
          <Move size={12} /> Cadrage horizontal · {Math.round(focalX * 100)}%
        </label>
        <input
          data-testid="editor-photo-focalx"
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={focalX}
          onChange={(e) => onChange({ focal_x: Number(e.target.value) })}
          className="w-full"
        />
      </div>

      <div>
        <label className="eyebrow block mb-2 flex items-center gap-2">
          <Move size={12} /> Cadrage vertical · {Math.round(focalY * 100)}%
        </label>
        <input
          data-testid="editor-photo-focaly"
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={focalY}
          onChange={(e) => onChange({ focal_y: Number(e.target.value) })}
          className="w-full"
        />
      </div>

      <button
        type="button"
        onClick={() => onChange({ scale: 1, focal_x: 0.5, focal_y: 0.5 })}
        className="w-full text-xs text-[color:var(--muted)] hover:text-[color:var(--ink)] underline underline-offset-4"
        data-testid="editor-photo-reset"
      >
        Réinitialiser le cadrage
      </button>

      <button
        type="button"
        onClick={onRemove}
        className="w-full inline-flex items-center justify-center gap-2 border border-red-300 text-red-600 py-2 hover:bg-red-50 transition-colors"
      >
        <Trash2 size={14} />
        <span className="text-xs font-semibold tracking-widest uppercase">
          Retirer de la page
        </span>
      </button>
    </div>
  );
}

function ProcessingScreen({ title }) {
  const [dots, setDots] = useState(0);
  const [stage, setStage] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setDots((d) => (d + 1) % 4), 500);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const t = setInterval(() => setStage((s) => (s + 1) % PROCESSING_STAGES.length), 2000);
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
          {PROCESSING_STAGES[stage]}
          {".".repeat(dots)}
        </p>
      </div>
    </main>
  );
}