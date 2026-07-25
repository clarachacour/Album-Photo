import React, { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { DEFAULT_COVER, defaultLogoItem, getTemplate } from "@/lib/coverTemplates";
import { makeCoverEditingActions, cryptoRandom } from "@/lib/coverEditing";
import { CoverFrontPage, CoverBackPage } from "@/components/AlbumPage";
import { CoverSpine } from "@/components/CoverSpine";
import { CoverEditorPanel } from "@/components/CoverEditorPanel";
import { TID } from "@/constants/testIds";
import { ArrowRight, ArrowLeft, Upload, Loader2, Sparkles, X } from "lucide-react";

const STEPS = ["Format", "Edit", "Pictures"];

function defaultCoverPayload() {
  const year = new Date().getFullYear();
  return {
    bg_color: DEFAULT_COVER.bg_color,
    accent_color: DEFAULT_COVER.accent_color,
    text_color: DEFAULT_COVER.text_color,
    title_font: DEFAULT_COVER.title_font,
    title_font_weight: DEFAULT_COVER.title_font_weight,
    extra_items: [defaultLogoItem()],
    back_extra_items: [
      {
        id: cryptoRandom(),
        type: "text",
        role: "country",
        content: "",
        x: 0.1,
        y: 0.46,
        w: 0.8,
        h: 0.08,
        font: "'Manrope', sans-serif",
        font_weight: "600",
        font_size: 16,
        color: DEFAULT_COVER.text_color,
      },
      {
        id: cryptoRandom(),
        type: "text",
        role: "year",
        content: String(year),
        x: 0.4,
        y: 0.86,
        w: 0.2,
        h: 0.06,
        font: "'Manrope', sans-serif",
        font_size: 11,
        color: DEFAULT_COVER.text_color,
      },
    ],
  };
}

export default function CreateAlbum() {
  const [step, setStep] = useState(0);
  const [size, setSize] = useState("A4");
  const [orientation, setOrientation] = useState("portrait");
  const [album, setAlbum] = useState(null); // created once we leave the Format step
  const [coverSel, setCoverSel] = useState(null);
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef();
  const nav = useNavigate();

  const template = getTemplate();
  const { updateCover, updateAlbumTitle, updateCoverItem, addCoverText, addCoverShape, addCoverImage, removeCoverItem } =
    makeCoverEditingActions({ setAlbum, albumId: album?.id, coverSel, setCoverSel });

  const handleFiles = (list) => {
    const arr = Array.from(list).filter((f) => f.type.startsWith("image/"));
    setFiles((prev) => [...prev, ...arr]);
  };
  const removeFile = (idx) => setFiles((prev) => prev.filter((_, i) => i !== idx));

  // Format -> Edit: create the album the first time, or persist size/orientation if we're revisiting.
  const goToEdit = async () => {
    setBusy(true);
    try {
      if (!album) {
        const { data } = await api.post("/albums", { size, orientation, cover: defaultCoverPayload() });
        setAlbum(data);
      } else {
        await api.patch(`/albums/${album.id}`, { size, orientation });
      }
      setStep(1);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Erreur lors de la création de l'album");
    } finally {
      setBusy(false);
    }
  };

  // Edit -> Pictures: persist title/cover customization.
  const goToPictures = async () => {
    if (!album) return;
    setBusy(true);
    try {
      await api.patch(`/albums/${album.id}`, { title: album.title, country: album.country, year: album.year, cover: album.cover || {} });
      setStep(2);
    } catch {
      toast.error("Enregistrement impossible");
    } finally {
      setBusy(false);
    }
  };

  const next = () => {
    if (step === 0) return goToEdit();
    if (step === 1) return goToPictures();
  };
  const prev = () => setStep((s) => Math.max(s - 1, 0));

  const canProceed = () => {
    if (step === 2) return files.length > 0;
    return true;
  };

  const createAndProcess = async () => {
    if (!album) return;
    setBusy(true);
    try {
      const chunkSize = 8;
      for (let i = 0; i < files.length; i += chunkSize) {
        const chunk = files.slice(i, i + chunkSize);
        const form = new FormData();
        chunk.forEach((f) => form.append("files", f));
        await api.post(`/albums/${album.id}/photos`, form, {
          headers: { "Content-Type": "multipart/form-data" },
        });
      }
      await api.post(`/albums/${album.id}/process`);
      toast.success("AI is composing your album...");
      nav(`/editor/${album.id}?processing=1`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Error during creation");
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen bg-[color:var(--paper)] pt-24 pb-24 px-6 md:px-12">
      <div className="max-w-[1400px] mx-auto">
        {/* Stepper */}
        <div className="flex items-center gap-4 mb-14">
          {STEPS.map((s, i) => (
            <div key={i} className="flex items-center gap-4">
              <div
                className={`w-6 h-6 flex items-center justify-center text-[10px] font-semibold ${
                  i <= step ? "bg-[color:var(--ink)] text-[color:var(--paper)]" : "bg-[color:var(--editor-canvas)] text-[color:var(--muted)]"
                }`}
              >
                {i + 1}
              </div>
              <span className={`eyebrow ${i === step ? "text-[color:var(--ink)]" : "text-[color:var(--muted)]"}`}>{s}</span>
              {i < STEPS.length - 1 && <div className="w-8 h-px bg-[color:var(--border-soft)]" />}
            </div>
          ))}
        </div>

        {step === 0 && <StepFormat size={size} setSize={setSize} orientation={orientation} setOrientation={setOrientation} template={template} />}

        {step === 1 && album && (
          <StepEdit
            album={album}
            orientation={orientation}
            template={template}
            coverSel={coverSel}
            setCoverSel={setCoverSel}
            updateCover={updateCover}
            updateAlbumTitle={updateAlbumTitle}
            updateCoverItem={updateCoverItem}
            addCoverText={addCoverText}
            addCoverShape={addCoverShape}
            addCoverImage={addCoverImage}
            removeCoverItem={removeCoverItem}
          />
        )}

        {step === 2 && (
          <StepPhotos files={files} handleFiles={handleFiles} removeFile={removeFile} fileInput={fileInput} />
        )}

        {/* Nav buttons */}
        <div className="mt-16 flex items-center justify-between">
          <button
            data-testid={TID.wizardBack}
            onClick={step === 0 ? () => nav("/dashboard") : prev}
            className="inline-flex items-center gap-3 text-sm font-semibold tracking-widest uppercase text-[color:var(--muted)] hover:text-[color:var(--ink)] transition-colors"
          >
            <ArrowLeft size={16} /> {step === 0 ? "Cancel" : "Back"}
          </button>
          {step < STEPS.length - 1 ? (
            <button
              data-testid={TID.wizardNext}
              onClick={next}
              disabled={!canProceed() || busy}
              className="inline-flex items-center gap-3 bg-[color:var(--ink)] text-[color:var(--paper)] px-10 py-4 hover:bg-[color:var(--coral)] transition-colors disabled:opacity-40"
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : <span className="text-sm font-semibold tracking-widest uppercase">Continue</span>}
              {!busy && <ArrowRight size={16} />}
            </button>
          ) : (
            <button
              data-testid={TID.wizardStartAi}
              onClick={createAndProcess}
              disabled={!canProceed() || busy}
              className="inline-flex items-center gap-3 bg-[color:var(--coral)] text-[color:var(--paper)] px-10 py-4 hover:bg-[color:var(--ink)] transition-colors disabled:opacity-60"
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
              <span className="text-sm font-semibold tracking-widest uppercase">Create Album</span>
            </button>
          )}
        </div>
      </div>
    </main>
  );
}

// -------------------- STEP COMPONENTS --------------------

function StepFormat({ size, setSize, orientation, setOrientation, template }) {
  const getAspectClass = () => (orientation === "landscape" ? "aspect-[1.414/1]" : "aspect-[1/1.414]");
  const sizeContainerStyle = {
    maxWidth: orientation === "landscape" ? (size === "A4" ? "560px" : "440px") : (size === "A4" ? "400px" : "320px"),
  };

  return (
    <section className="animate-fade-up grid grid-cols-1 md:grid-cols-2 gap-16">
      <div>
        <h2 className="font-serif-display text-4xl md:text-5xl tracking-tight mb-3">Format & orientation.</h2>
        <p className="text-[color:var(--ink)]/70 mb-10">The final printable output. You'll design your cover right after.</p>
        <div className="mb-10">
          <div className="eyebrow mb-4">Size</div>
          <div className="flex gap-3">
            {["A4", "A5"].map((s) => (
              <button
                key={s}
                data-testid={TID.sizeOption}
                data-size={s}
                onClick={() => setSize(s)}
                className={`px-6 py-3 border ${
                  size === s
                    ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
                    : "border-[color:var(--ink)]/30 text-[color:var(--ink)] hover:border-[color:var(--ink)]"
                } transition-colors`}
              >
                <span className="font-semibold tracking-widest text-sm">{s}</span>
              </button>
            ))}
          </div>
        </div>
        <div>
          <div className="eyebrow mb-4">Orientation</div>
          <div className="flex gap-3">
            {[
              { v: "portrait", l: "Portrait" },
              { v: "landscape", l: "Landscape" },
            ].map((o) => (
              <button
                key={o.v}
                data-testid={TID.orientationOption}
                data-orientation={o.v}
                onClick={() => setOrientation(o.v)}
                className={`px-6 py-3 border ${
                  orientation === o.v
                    ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
                    : "border-[color:var(--ink)]/30 text-[color:var(--ink)] hover:border-[color:var(--ink)]"
                } transition-colors`}
              >
                <span className="font-semibold tracking-widest text-sm">{o.l}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="flex items-center justify-center">
        <div className="bg-[color:var(--editor-canvas)] p-8 transition-all duration-300 flex items-center justify-center w-full">
          <div
            className={`${getAspectClass()} bg-white relative transition-all duration-300 shadow-sm`}
            style={{ background: template.bg, width: "100%", ...sizeContainerStyle }}
          >
            <div className="absolute inset-0 grain" />
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="font-serif-display text-xl md:text-2xl" style={{ color: template.text }}>
                {size} · {orientation === "landscape" ? "landscape" : "portrait"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function StepEdit({
  album,
  orientation,
  template,
  coverSel,
  setCoverSel,
  updateCover,
  updateAlbumTitle,
  updateCoverItem,
  addCoverText,
  addCoverShape,
  addCoverImage,
  removeCoverItem,
}) {
  const cover = album.cover || {};

  return (
    <section className="animate-fade-up grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-10">
      <div>
        <div className="mb-8 max-w-2xl">
          <h2 className="font-serif-display text-4xl md:text-5xl tracking-tight mb-3">Make it yours.</h2>
          <p className="text-[color:var(--ink)]/70">
            Click the title, the logo, or the text on the back to edit them directly. Drag to move or resize. Add your own
            image or text anywhere on the cover.
          </p>
        </div>
        <div className="grid grid-cols-[1fr_32px_1fr] gap-0 rounded-sm overflow-hidden book-shadow max-w-3xl mx-auto">
          <CoverBackPage
            template={template}
            country={album.country}
            year={album.year}
            orientation={orientation}
            cover={cover}
            editable
            onSelectCover={() => setCoverSel({ mode: "cover", side: "back" })}
            onSelectItem={(item) => setCoverSel({ mode: "item", side: "back", itemId: item.id })}
            onUpdateItem={(itemId, patch) => updateCoverItem(itemId, patch, "back")}
            selectedItemId={coverSel?.mode === "item" && coverSel?.side === "back" ? coverSel.itemId : null}
          />
          <CoverSpine
            title={album.title}
            year={album.year}
            template={template}
            cover={cover}
            editable
            selectedZone={coverSel?.mode}
            onSelectTitle={() => setCoverSel({ mode: "spine-title" })}
            onSelectYear={() => setCoverSel({ mode: "spine-year" })}
            onUpdateCover={updateCover}
          />
          <CoverFrontPage
            template={template}
            title={album.title}
            orientation={orientation}
            coverImageUrl={null}
            cover={cover}
            editable
            onSelectCover={() => setCoverSel({ mode: "cover", side: "front" })}
            onSelectTitle={() => setCoverSel({ mode: "title", side: "front" })}
            onSelectItem={(item) => setCoverSel({ mode: "item", side: "front", itemId: item.id })}
            onUpdateTitle={(patch) => updateCover(patch)}
            onUpdateItem={(itemId, patch) => updateCoverItem(itemId, patch, "front")}
            titleSelected={coverSel?.mode === "title"}
            selectedItemId={coverSel?.mode === "item" && coverSel?.side === "front" ? coverSel.itemId : null}
          />
        </div>
      </div>
      <div>
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
        ) : (
          <div className="text-sm text-[color:var(--muted)] border border-dashed border-[color:var(--border-soft)] p-6">
            Click any element on the cover — the title, the logo, the text on the back — to edit, move, or remove it.
          </div>
        )}
      </div>
    </section>
  );
}

function StepPhotos({ files, handleFiles, removeFile, fileInput }) {
  const [drag, setDrag] = useState(false);
  return (
    <section className="animate-fade-up">
      <h2 className="font-serif-display text-4xl md:text-5xl tracking-tight mb-3">Drop your photos.</h2>
      <p className="text-[color:var(--ink)]/70 mb-10">
        All your photos, in any order. The AI will handle the rest: sorting, duplicates, layout.
      </p>

      <div
        data-testid={TID.photoDropzone}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => fileInput.current?.click()}
        className={`border-2 border-dashed cursor-pointer p-16 text-center transition-colors ${
          drag ? "border-[color:var(--coral)] bg-[color:var(--coral)]/5" : "border-[color:var(--ink)]/20 hover:border-[color:var(--ink)]/50"
        }`}
      >
        <Upload size={32} className="mx-auto mb-4 text-[color:var(--muted)]" />
        <p className="font-serif-display text-2xl mb-2">Drag your images here</p>
        <p className="text-[color:var(--muted)] text-sm">or click to browse · JPG, PNG, WEBP</p>
        <input
          ref={fileInput}
          data-testid={TID.photoInput}
          type="file"
          multiple
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {files.length > 0 && (
        <div className="mt-10">
          <div className="eyebrow mb-4">{files.length} photo{files.length > 1 ? "s" : ""} · AI will choose the best ones</div>
          <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-8 gap-2">
            {files.map((f, i) => (
              <div key={i} className="relative aspect-square bg-[color:var(--editor-canvas)] overflow-hidden group">
                <img src={URL.createObjectURL(f)} alt="" className="w-full h-full object-cover" />
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    removeFile(i);
                  }}
                  className="absolute top-1 right-1 bg-[color:var(--ink)] text-white p-1 opacity-0 group-hover:opacity-100 transition-opacity"
                  aria-label="Remove"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}