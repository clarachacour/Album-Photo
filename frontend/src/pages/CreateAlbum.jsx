import React, { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { DEFAULT_COVER, defaultLogoItem, getTemplate } from "@/lib/coverTemplates";
import { findTemplate } from "@/lib/coverThemes";
import { makeCoverEditingActions, cryptoRandom } from "@/lib/coverEditing";
import { CoverFrontPage, CoverBackPage } from "@/components/AlbumPage";
import { CoverSpine } from "@/components/CoverSpine";
import { spineRatio, DEFAULT_PAGE_COUNT_ESTIMATE } from "@/lib/printDims";
import { CoverEditorPanel } from "@/components/CoverEditorPanel";
import PhotoUploadMethods from "@/components/PhotoUploadMethods";
import { TID } from "@/constants/testIds";
import { useHistoryState } from "@/lib/useHistoryState";
import { ArrowRight, ArrowLeft, Loader2, Sparkles } from "lucide-react";

const STEPS = ["Format", "Edit", "Pictures"];

function defaultCoverPayload(chosenTemplate) {
  const year = new Date().getFullYear();
  const tplCover = chosenTemplate?.cover || {};
  return {
    bg_color: DEFAULT_COVER.bg_color,
    accent_color: DEFAULT_COVER.accent_color,
    text_color: DEFAULT_COVER.text_color,
    title_font: DEFAULT_COVER.title_font,
    title_font_weight: DEFAULT_COVER.title_font_weight,
    // Spread every field the template sets (colors, title size/position, spine
    // subtitle, or anything added later) — nothing gets silently dropped just
    // because this function wasn't updated to know about a new field name.
    ...tplCover,
    extra_items: tplCover.extra_items ? tplCover.extra_items.map((it) => ({ ...it, id: cryptoRandom() })) : [defaultLogoItem()],
    back_extra_items: tplCover.back_extra_items ? tplCover.back_extra_items.map((it) => ({ ...it, id: cryptoRandom() })) : [
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
        text_align: "center",
        color: tplCover.text_color ?? DEFAULT_COVER.text_color,
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
        text_align: "center",
        color: tplCover.text_color ?? DEFAULT_COVER.text_color,
      },
    ],
  };
}

const CREATION_STAGES = [
  "Analyzing images…",
  "Detecting duplicates…",
  "Grouping by scene…",
  "Composing pages…",
];

function CreationProgressScreen({ progress }) {
  const [stage, setStage] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setStage((s) => (s + 1) % CREATION_STAGES.length), 2200);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="fixed inset-0 bg-[color:var(--paper)] flex items-center justify-center z-50">
      <div className="absolute inset-0 grain pointer-events-none" />
      <div className="text-center max-w-lg px-6 relative">
        <Sparkles size={32} className="mx-auto text-[color:var(--coral)] mb-8 animate-slow-pulse" />
        <div className="eyebrow mb-4">AI is composing your edition</div>
        <div className="font-serif-display text-6xl md:text-7xl tracking-tight mb-6">
          {Math.round(progress)}%
        </div>
        <div className="w-64 h-1 bg-[color:var(--border-soft)] mx-auto mb-8 overflow-hidden">
          <div
            className="h-full bg-[color:var(--coral)] transition-all duration-300 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="font-serif-display text-xl md:text-2xl text-[color:var(--muted)] italic">
          {CREATION_STAGES[stage]}
        </p>
        <p className="text-sm text-[color:var(--muted)] mt-6">
          This can take a few minutes for a large album — feel free to stay on this page.
        </p>
      </div>
    </div>
  );
}

export default function CreateAlbum() {
  const [params] = useSearchParams();
  const resumeAlbumId = params.get("albumId");
  const chosenTemplate = findTemplate(params.get("template"));
  const [step, setStep] = useState(0);
  const [size, setSize] = useState("A4");
  const [orientation, setOrientation] = useState("portrait");
  const [targetPages, setTargetPages] = useState(50);
  const [album, setAlbum, albumHistory] = useHistoryState(null); // created once we leave the Format step
  const [coverSel, setCoverSel] = useState(null);
  const [serverPhotos, setServerPhotos] = useState([]);
  const [busy, setBusy] = useState(false);
  const [creationProgress, setCreationProgress] = useState(0);
  const [resuming, setResuming] = useState(!!resumeAlbumId);
  const nav = useNavigate();

  useEffect(() => {
    if (!resumeAlbumId) return;
    (async () => {
      try {
        const { data } = await api.get(`/albums/${resumeAlbumId}`);
        albumHistory.resetState(data);
        setServerPhotos(data.photos || []);
        setSize(data.size || "A4");
        setOrientation(data.orientation || "portrait");
        setTargetPages(data.target_pages || 50);
        setStep(2); // straight to Pictures — cover/format were already set
      } catch {
        toast.error("Could not load this album");
        nav("/dashboard");
      } finally {
        setResuming(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resumeAlbumId]);

  const template = getTemplate();
  const { updateCover, updateCoverTitle, updateAlbumTitle, updateAlbumYear, updateCoverItem, addCoverText, addCoverShape, addCoverImage, removeCoverItem } =
    makeCoverEditingActions({ setAlbum, albumId: album?.id, coverSel, setCoverSel });

  useEffect(() => {
    const onKeyDown = (e) => {
      const tag = document.activeElement?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || document.activeElement?.isContentEditable) return;

      const isMod = e.ctrlKey || e.metaKey;
      if (isMod && !e.shiftKey && e.key.toLowerCase() === "z") {
        e.preventDefault();
        albumHistory.undo();
        return;
      }
      if (isMod && (e.key.toLowerCase() === "y" || (e.shiftKey && e.key.toLowerCase() === "z"))) {
        e.preventDefault();
        albumHistory.redo();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);


  // Format -> Edit: create the album the first time, or persist size/orientation if we're revisiting.
  const goToEdit = async () => {
    setBusy(true);
    try {
      if (!album) {
        const { data } = await api.post("/albums", {
          size,
          orientation,
          target_pages: targetPages,
          title: chosenTemplate?.title || "Untitled",
          cover_template_id: chosenTemplate?.id || "default",
          cover: defaultCoverPayload(chosenTemplate),
        });
        albumHistory.resetState(data);
      } else {
        await api.patch(`/albums/${album.id}`, { size, orientation, target_pages: targetPages });
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
    if (step === 2) return serverPhotos.length >= minimumRequiredPhotos(targetPages);
    return true;
  };

  const createAndProcess = async () => {
    if (!album) return;
    setBusy(true);
    setCreationProgress(0);
    // There's no real progress to report back from a single blocking API
    // call, so this eases toward 90% over time (asymptotically, never
    // quite reaching it) — honest, reassuring movement during what can be
    // a multi-minute wait for a large album, without pretending to know
    // exactly how far along the AI actually is.
    const interval = setInterval(() => {
      setCreationProgress((p) => (p < 90 ? p + (90 - p) * 0.06 : p));
    }, 400);
    try {
      await api.post(`/albums/${album.id}/process`);
      clearInterval(interval);
      setCreationProgress(100);
      toast.success("AI is composing your album...");
      setTimeout(() => nav(`/editor/${album.id}?processing=1`), 500);
    } catch (err) {
      clearInterval(interval);
      toast.error(err?.response?.data?.detail || "Error during creation");
      setBusy(false);
      setCreationProgress(0);
    }
  };

  if (busy && step === 2) {
    return <CreationProgressScreen progress={creationProgress} />;
  }

  if (resuming) {
    return (
      <main className="min-h-screen bg-[color:var(--paper)] flex items-center justify-center">
        <Loader2 className="animate-spin text-[color:var(--muted)]" size={28} />
      </main>
    );
  }

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

        {step === 0 && <StepFormat size={size} setSize={setSize} orientation={orientation} setOrientation={setOrientation} targetPages={targetPages} setTargetPages={setTargetPages} />}

        {step === 1 && album && (
          <StepEdit
            album={album}
            size={size}
            orientation={orientation}
            targetPages={targetPages}
            template={template}
            coverSel={coverSel}
            setCoverSel={setCoverSel}
            updateCover={updateCover}
            updateCoverTitle={updateCoverTitle}
            updateAlbumTitle={updateAlbumTitle}
            updateAlbumYear={updateAlbumYear}
            updateCoverItem={updateCoverItem}
            addCoverText={addCoverText}
            addCoverShape={addCoverShape}
            addCoverImage={addCoverImage}
            removeCoverItem={removeCoverItem}
          />
        )}

        {step === 2 && (
          <StepPhotos
            albumId={album?.id}
            serverPhotos={serverPhotos}
            onServerPhotosChange={setServerPhotos}
            targetPages={targetPages}
            onBack={prev}
            onCreate={createAndProcess}
            canCreate={canProceed()}
            busy={busy}
          />
        )}

        {/* Nav buttons — hidden on the Photos step, where these same
            actions are shown right under the upload buttons instead (see
            StepPhotos' afterMethodsRow), so they're never a long scroll
            away with hundreds of photos uploaded. */}
        {step !== 2 && (
          <div className="mt-16 flex items-center justify-between">
            <button
              data-testid={TID.wizardBack}
              onClick={step === 0 ? () => nav("/dashboard") : prev}
              className="inline-flex items-center gap-3 text-sm font-semibold tracking-widest uppercase text-[color:var(--muted)] hover:text-[color:var(--ink)] transition-colors"
            >
              <ArrowLeft size={16} /> {step === 0 ? "Cancel" : "Back"}
            </button>
            <button
              data-testid={TID.wizardNext}
              onClick={next}
              disabled={!canProceed() || busy}
              className="inline-flex items-center gap-3 bg-[color:var(--ink)] text-[color:var(--paper)] px-10 py-4 hover:bg-[color:var(--coral)] transition-colors disabled:opacity-40"
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : <span className="text-sm font-semibold tracking-widest uppercase">Continue</span>}
              {!busy && <ArrowRight size={16} />}
            </button>
          </div>
        )}
      </div>
    </main>
  );
}

// -------------------- STEP COMPONENTS --------------------

const PAGE_TIERS = [24, 50, 100, 150, 250];

function StepFormat({ size, setSize, orientation, setOrientation, targetPages, setTargetPages }) {
  const getAspectClass = () => (orientation === "landscape" ? "aspect-[1.414/1]" : "aspect-[1/1.414]");
  const maxWidthBySize = { A3: 640, A4: 500, A5: 400 };
  const sizeContainerStyle = {
    maxWidth: `${orientation === "landscape" ? maxWidthBySize[size] : maxWidthBySize[size] * 0.72}px`,
  };
  const isCustom = !PAGE_TIERS.includes(targetPages);

  return (
    <section className="animate-fade-up grid grid-cols-1 md:grid-cols-2 gap-16">
      <div>
        <h2 className="font-serif-display text-4xl md:text-5xl tracking-tight mb-3">Format & orientation.</h2>
        <p className="text-[color:var(--ink)]/70 mb-10">The final printable output. You'll design your cover right after.</p>
        <div className="mb-10">
          <div className="eyebrow mb-4">Size</div>
          <div className="flex gap-3">
            {["A3", "A4", "A5"].map((s) => (
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
        <div className="mb-10">
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
        <div>
          <div className="eyebrow mb-4">Number of pages</div>
          <div className="flex flex-wrap gap-3">
            {PAGE_TIERS.map((t) => (
              <button
                key={t}
                onClick={() => setTargetPages(t)}
                className={`px-6 py-3 border ${
                  targetPages === t
                    ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
                    : "border-[color:var(--ink)]/30 text-[color:var(--ink)] hover:border-[color:var(--ink)]"
                } transition-colors`}
              >
                <span className="font-semibold tracking-widest text-sm">{t}p</span>
              </button>
            ))}
            <button
              onClick={() => setTargetPages(isCustom ? targetPages : PAGE_TIERS[PAGE_TIERS.length - 1] + 1)}
              className={`px-6 py-3 border ${
                isCustom
                  ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
                  : "border-[color:var(--ink)]/30 text-[color:var(--ink)] hover:border-[color:var(--ink)]"
              } transition-colors`}
            >
              <span className="font-semibold tracking-widest text-sm">Custom</span>
            </button>
          </div>
          {isCustom && (
            <div className="mt-4">
              <input
                type="number"
                min={1}
                value={targetPages}
                onChange={(e) => setTargetPages(Math.max(1, parseInt(e.target.value, 10) || 1))}
                className="w-32 px-4 py-2 border border-[color:var(--ink)]/30 focus:border-[color:var(--ink)] outline-none"
              />
              <span className="text-sm text-[color:var(--ink)]/60 ml-3">pages — priced above the nearest standard tier</span>
            </div>
          )}
        </div>
      </div>
      <div className="flex items-center justify-center">
        <div className="bg-[color:var(--editor-canvas)] p-8 transition-all duration-300 flex items-center justify-center w-full">
          <div
            className={`${getAspectClass()} relative transition-all duration-300 shadow-sm border border-[color:var(--border-soft)]`}
            style={{ background: "#E4E1D8", width: "100%", ...sizeContainerStyle }}
          >
            <div className="absolute inset-0 grain" />
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="font-serif-display text-xl md:text-2xl text-[color:var(--ink)]/60">
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
  size,
  orientation,
  targetPages,
  template,
  coverSel,
  setCoverSel,
  updateCover,
  updateCoverTitle,
  updateAlbumTitle,
  updateAlbumYear,
  updateCoverItem,
  addCoverText,
  addCoverShape,
  addCoverImage,
  removeCoverItem,
}) {
  const cover = album.cover || {};
  // No photos uploaded yet at this step (cover editing comes before the
  // "Pictures" step), so the *final* page count (after AI curation) isn't
  // known yet — but the person's chosen target_pages already is (set back
  // in the Format step), and is a much more accurate stand-in than a fixed
  // generic estimate: a 200-page album now visibly gets a thicker spine
  // than a 20-page one immediately, instead of both looking identical
  // until the AI actually runs. AlbumEditor.jsx switches to the real,
  // final album.pages.length once that's known.
  const spineFr = spineRatio(size, orientation, targetPages || DEFAULT_PAGE_COUNT_ESTIMATE);

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
        <div
          className="grid gap-[3px] rounded-sm overflow-hidden book-shadow max-w-3xl mx-auto bg-[color:var(--ink)]/70"
          style={{ gridTemplateColumns: `1fr ${spineFr}fr 1fr` }}
        >
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
            onSelectCaption={() => setCoverSel({ mode: "spine-caption" })}
            onSelectLogo={() => setCoverSel({ mode: "spine-logo" })}
            onSelectDivider={() => setCoverSel({ mode: "spine-divider" })}
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
            onUpdateTitle={updateCoverTitle}
            onTitleTextChange={updateAlbumTitle}
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
            updateAlbumYear={updateAlbumYear}
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

// Derived from LAYOUT_PATTERN's 7 templates (single_full=1, dual_vertical=2,
// hero_strip=4, single_centered=1, quad_grid=4, triptych=3,
// dual_horizontal=2 photos each) — kept in sync with the backend's layout
// logic in server.py. A 1.3x margin accounts for photos the AI rejects as
// duplicates or too blurry, so this is a recommendation, not a guarantee —
// actual results still depend on the quality of what's uploaded.
const AVG_PHOTOS_PER_PAGE = 17 / 7;
const CURATION_SAFETY_MARGIN = 1.3;

function recommendedMinPhotos(targetPages) {
  const contentPages = Math.max(0, (targetPages || 0) - 1); // minus the title page
  return Math.ceil(contentPages * AVG_PHOTOS_PER_PAGE * CURATION_SAFETY_MARGIN);
}

// The absolute floor: since the layout always uses at least 1 photo per
// page, filling `targetPages` pages is mathematically impossible with
// fewer than this many photos, no matter how good they are — unlike
// recommendedMinPhotos (a soft heuristic accounting for expected curation
// losses), this one is a hard guarantee and blocks proceeding rather than
// just warning.
function minimumRequiredPhotos(targetPages) {
  return Math.max(0, (targetPages || 0) - 1);
}

function StepPhotos({ albumId, serverPhotos, onServerPhotosChange, targetPages, onBack, onCreate, canCreate, busy }) {
  const recommended = recommendedMinPhotos(targetPages);
  const minimum = minimumRequiredPhotos(targetPages);
  const uploaded = serverPhotos.length;
  const enough = uploaded >= recommended;
  const belowMinimum = uploaded < minimum;

  return (
    <section className="animate-fade-up">
      <h2 className="font-serif-display text-4xl md:text-5xl tracking-tight mb-3">Drop your photos.</h2>
      <p className="text-[color:var(--ink)]/70 mb-4">
        All your photos, in any order. The AI will handle the rest: sorting, duplicates, layout.
      </p>
      <div
        className={`text-sm border rounded px-4 py-3 mb-6 ${
          belowMinimum
            ? "text-red-700 bg-red-50 border-red-200"
            : enough
            ? "text-emerald-700 bg-emerald-50 border-emerald-200"
            : "text-amber-700 bg-amber-50 border-amber-200"
        }`}
      >
        {belowMinimum
          ? `${uploaded} of at least ${minimum} photos required for a ${targetPages}-page album — upload ${minimum - uploaded} more to continue, or choose a smaller page count.`
          : enough
          ? `${uploaded} photos uploaded — that's enough for your ${targetPages}-page album.`
          : `${uploaded} of the ~${recommended} photos we recommend for a ${targetPages}-page album (some will be rejected as duplicates or too blurry — upload more to fill every page).`}
      </div>
      <PhotoUploadMethods
        albumId={albumId}
        mode="wizard"
        photos={serverPhotos}
        onPhotosChange={onServerPhotosChange}
        afterMethodsRow={
          <div className="my-6 flex items-center justify-between border-y border-[color:var(--border-soft)] py-4">
            <button
              onClick={onBack}
              className="inline-flex items-center gap-3 text-sm font-semibold tracking-widest uppercase text-[color:var(--muted)] hover:text-[color:var(--ink)] transition-colors"
            >
              <ArrowLeft size={16} /> Back
            </button>
            <button
              onClick={onCreate}
              disabled={!canCreate || busy}
              className="inline-flex items-center gap-3 bg-[color:var(--coral)] text-[color:var(--paper)] px-10 py-4 hover:bg-[color:var(--ink)] transition-colors disabled:opacity-60"
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
              <span className="text-sm font-semibold tracking-widest uppercase">Create Album</span>
            </button>
          </div>
        }
      />
    </section>
  );
}
