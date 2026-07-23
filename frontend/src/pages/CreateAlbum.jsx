import React, { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { COVER_TEMPLATES } from "@/lib/coverTemplates";
import { CoverMockup } from "@/components/CoverPreview";
import { TID } from "@/constants/testIds";
import { ArrowRight, ArrowLeft, Upload, Loader2, Sparkles, X } from "lucide-react";

const STEPS = ["Couverture", "Format", "Détails", "Photos"];

export default function CreateAlbum() {
  const [step, setStep] = useState(0);
  const [templateId, setTemplateId] = useState(COVER_TEMPLATES[0].id);
  const [size, setSize] = useState("A4");
  const [orientation, setOrientation] = useState("portrait");
  const [title, setTitle] = useState("");
  const [country, setCountry] = useState("");
  const [year, setYear] = useState(new Date().getFullYear());
  const [files, setFiles] = useState([]);
  const [albumId, setAlbumId] = useState(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef();
  const nav = useNavigate();

  const template = COVER_TEMPLATES.find((t) => t.id === templateId);

  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  const prev = () => setStep((s) => Math.max(s - 1, 0));

  const canProceed = () => {
    if (step === 2) return title.trim().length > 0;
    if (step === 3) return files.length > 0;
    return true;
  };

  const handleFiles = (list) => {
    const arr = Array.from(list).filter((f) => f.type.startsWith("image/"));
    setFiles((prev) => [...prev, ...arr]);
  };

  const removeFile = (idx) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const createAndProcess = async () => {
    setBusy(true);
    try {
      // 1. Create album
      const { data: album } = await api.post("/albums", {
        title: title.trim() || "Sans titre",
        country: country.trim(),
        year: Number(year) || new Date().getFullYear(),
        cover_template_id: templateId,
        size,
        orientation,
      });
      setAlbumId(album.id);

      // 2. Upload photos in chunks of 10
      const chunkSize = 8;
      for (let i = 0; i < files.length; i += chunkSize) {
        const chunk = files.slice(i, i + chunkSize);
        const form = new FormData();
        chunk.forEach((f) => form.append("files", f));
        await api.post(`/albums/${album.id}/photos`, form, {
          headers: { "Content-Type": "multipart/form-data" },
        });
      }

      // 3. Start AI processing (background)
      await api.post(`/albums/${album.id}/process`);
      toast.success("L'IA compose votre album…");
      nav(`/editor/${album.id}?processing=1`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Erreur lors de la création");
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

        {step === 0 && (
          <StepCover templateId={templateId} setTemplateId={setTemplateId} />
        )}
        {step === 1 && (
          <StepFormat size={size} setSize={setSize} orientation={orientation} setOrientation={setOrientation} template={template} />
        )}
        {step === 2 && (
          <StepDetails
            title={title}
            setTitle={setTitle}
            country={country}
            setCountry={setCountry}
            year={year}
            setYear={setYear}
            template={template}
          />
        )}
        {step === 3 && (
          <StepPhotos files={files} handleFiles={handleFiles} removeFile={removeFile} fileInput={fileInput} />
        )}

        {/* Nav buttons */}
        <div className="mt-16 flex items-center justify-between">
          <button
            data-testid={TID.wizardBack}
            onClick={step === 0 ? () => nav("/dashboard") : prev}
            className="inline-flex items-center gap-3 text-sm font-semibold tracking-widest uppercase text-[color:var(--muted)] hover:text-[color:var(--ink)] transition-colors"
          >
            <ArrowLeft size={16} /> {step === 0 ? "Annuler" : "Retour"}
          </button>
          {step < STEPS.length - 1 ? (
            <button
              data-testid={TID.wizardNext}
              onClick={next}
              disabled={!canProceed()}
              className="inline-flex items-center gap-3 bg-[color:var(--ink)] text-[color:var(--paper)] px-10 py-4 hover:bg-[color:var(--coral)] transition-colors disabled:opacity-40"
            >
              <span className="text-sm font-semibold tracking-widest uppercase">Continuer</span>
              <ArrowRight size={16} />
            </button>
          ) : (
            <button
              data-testid={TID.wizardStartAi}
              onClick={createAndProcess}
              disabled={!canProceed() || busy}
              className="inline-flex items-center gap-3 bg-[color:var(--coral)] text-[color:var(--paper)] px-10 py-4 hover:bg-[color:var(--ink)] transition-colors disabled:opacity-60"
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
              <span className="text-sm font-semibold tracking-widest uppercase">Lancer l'IA</span>
            </button>
          )}
        </div>
      </div>
    </main>
  );
}

// -------------------- STEP COMPONENTS --------------------
function StepCover({ templateId, setTemplateId }) {
  return (
    <section className="animate-fade-up">
      <div className="mb-10 max-w-2xl">
        <h2 className="font-serif-display text-4xl md:text-5xl tracking-tight mb-3">Choisissez votre couverture.</h2>
        <p className="text-[color:var(--ink)]/70">
          Six esthétiques inspirées des livres coffee-table. Vous pourrez personnaliser le titre et le pays juste après.
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-14">
        {COVER_TEMPLATES.map((tpl) => (
          <button
            key={tpl.id}
            data-testid={TID.templateCard}
            data-template-id={tpl.id}
            onClick={() => setTemplateId(tpl.id)}
            className={`text-left transition-all ${
              templateId === tpl.id ? "opacity-100" : "opacity-70 hover:opacity-100"
            }`}
          >
            <div className={`${templateId === tpl.id ? "ring-2 ring-[color:var(--coral)] ring-offset-4 ring-offset-[color:var(--paper)]" : ""}`}>
              <CoverMockup template={tpl} title={sampleTitle(tpl.id)} year={2026} />
            </div>
            <div className="mt-4">
              <div className="eyebrow">{tpl.name}</div>
              <div className="text-sm text-[color:var(--muted)] mt-1">{tpl.mood}</div>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

function sampleTitle(id) {
  return {
    "teal-coral": "Western Australia",
    "sand-forest": "Marrakech",
    "navy-blush": "Tokyo Neon",
    "terracotta-cream": "Sahara Sud",
    "forest-gold": "Nordic Trails",
    "charcoal-rose": "Paris Nocturne",
  }[id] || "Album";
}

function StepFormat({ size, setSize, orientation, setOrientation, template }) {
  return (
    <section className="animate-fade-up grid grid-cols-1 md:grid-cols-2 gap-16">
      <div>
        <h2 className="font-serif-display text-4xl md:text-5xl tracking-tight mb-3">Format & orientation.</h2>
        <p className="text-[color:var(--ink)]/70 mb-10">Le rendu final imprimable.</p>
        <div className="mb-10">
          <div className="eyebrow mb-4">Taille</div>
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
              { v: "landscape", l: "Paysage" },
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
        <div
          className={`bg-[color:var(--editor-canvas)] p-8 ${
            orientation === "landscape" ? "w-full max-w-[520px]" : "w-full max-w-[380px]"
          }`}
        >
          <div className={`${orientation === "landscape" ? "aspect-[1.414/1]" : "aspect-[1/1.414]"} bg-white relative`} style={{ background: template.bg }}>
            <div className="absolute inset-0 grain" />
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="font-serif-display text-2xl" style={{ color: template.text }}>
                {size} · {orientation === "landscape" ? "paysage" : "portrait"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function StepDetails({ title, setTitle, country, setCountry, year, setYear, template }) {
  return (
    <section className="animate-fade-up grid grid-cols-1 md:grid-cols-2 gap-16">
      <div>
        <h2 className="font-serif-display text-4xl md:text-5xl tracking-tight mb-3">Le titre & le lieu.</h2>
        <p className="text-[color:var(--ink)]/70 mb-10">Ils apparaîtront sur la couverture, la reliure et l'arrière du livre.</p>
        <div className="space-y-8 max-w-md">
          <div>
            <label className="eyebrow block mb-2">Titre</label>
            <input
              data-testid={TID.wizardTitleInput}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="ex. Western Australia"
              className="w-full bg-transparent border-0 border-b border-[color:var(--ink)]/30 focus:border-[color:var(--ink)] focus:outline-none py-3 font-serif-display text-2xl"
            />
          </div>
          <div>
            <label className="eyebrow block mb-2">Pays / lieu</label>
            <input
              data-testid={TID.wizardCountryInput}
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              placeholder="ex. Australia"
              className="w-full bg-transparent border-0 border-b border-[color:var(--ink)]/30 focus:border-[color:var(--ink)] focus:outline-none py-3 font-serif-display text-2xl"
            />
          </div>
          <div>
            <label className="eyebrow block mb-2">Année</label>
            <input
              data-testid={TID.wizardYearInput}
              type="number"
              value={year}
              onChange={(e) => setYear(e.target.value)}
              className="w-full bg-transparent border-0 border-b border-[color:var(--ink)]/30 focus:border-[color:var(--ink)] focus:outline-none py-3 font-serif-display text-2xl"
            />
          </div>
        </div>
      </div>
      <div>
        <CoverMockup template={template} title={title || "Votre titre"} country={country || "Pays"} year={year} showLabels />
      </div>
    </section>
  );
}

function StepPhotos({ files, handleFiles, removeFile, fileInput }) {
  const [drag, setDrag] = useState(false);
  return (
    <section className="animate-fade-up">
      <h2 className="font-serif-display text-4xl md:text-5xl tracking-tight mb-3">Déposez vos photos.</h2>
      <p className="text-[color:var(--ink)]/70 mb-10">
        Toutes vos photos, dans le désordre. L'IA se chargera du reste : tri, doublons, mise en page.
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
        <p className="font-serif-display text-2xl mb-2">Glissez vos images ici</p>
        <p className="text-[color:var(--muted)] text-sm">ou cliquez pour parcourir · JPG, PNG, WEBP</p>
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
          <div className="eyebrow mb-4">{files.length} photo{files.length > 1 ? "s" : ""} · l'IA choisira les meilleures</div>
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
                  aria-label="Retirer"
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
