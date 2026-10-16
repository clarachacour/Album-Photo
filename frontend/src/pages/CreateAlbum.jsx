import React, { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { DEFAULT_COVER, defaultLogoItem, getTemplate } from "@/lib/coverTemplates";
import { findTemplate, templateFormat } from "@/lib/coverThemes";
import { makeCoverEditingActions, cryptoRandom } from "@/lib/coverEditing";
import { CoverFrontPage } from "@/components/book/CoverFrontPage";
import { CoverBackPage } from "@/components/book/CoverBackPage";
import { CoverSpine } from "@/components/CoverSpine";
import { spineRatio, pageDimsMm, DEFAULT_PAGE_COUNT_ESTIMATE } from "@/lib/printDims";
import { computeUnitPrice, computeDigitalPrice, PAGE_TIERS } from "@/lib/pricing";
import { CoverEditorPanel } from "@/components/CoverEditorPanel";
import PhotoUploadMethods from "@/components/PhotoUploadMethods";
import { TID } from "@/constants/testIds";
import { useHistoryState } from "@/lib/useHistoryState";
import { HistoryPreviewContext } from "@/lib/historyPreview";
import { ArrowRight, ArrowLeft, Loader2, Sparkles, Undo2, Redo2 } from "lucide-react";
import { usePageMeta } from "@/hooks/usePageMeta";
import { useGuidedTour, TourHelpButton } from "@/components/tour/GuidedTour";
import { COVER_TOUR } from "@/components/tour/tours";
import { useDeselectOutside } from "@/lib/useDeselectOutside";

function defaultCoverPayload(chosenTemplate) {
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
    // template_item_id: lets "Reset position" find the element's place in
    // the template (see lib/coverDefaults.js).
    extra_items: tplCover.extra_items ? tplCover.extra_items.map((it) => ({ ...it, id: cryptoRandom(), template_item_id: it.id })) : [defaultLogoItem()],
    // No default back_extra_items — CoverBackPage already shows
    // album.country automatically (and gracefully renders nothing if it's
    // never been set) whenever there are no back_extra_items at all. A
    // pre-added-but-empty "country" text item here used to block that
    // automatic display without ever showing anything itself, and looked
    // like a mystery empty box to select and delete before this display
    // was even reachable.
    back_extra_items: tplCover.back_extra_items ? tplCover.back_extra_items.map((it) => ({ ...it, id: cryptoRandom(), template_item_id: it.id })) : [],
  };
}

function CreationProgressScreen({ progress }) {
  const { t } = useTranslation();
  const stages = t("createAlbum.creationStages", { returnObjects: true });
  const [stage, setStage] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setStage((s) => (s + 1) % stages.length), 2200);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div className="fixed inset-0 bg-[color:var(--paper)] flex items-center justify-center z-50">
      <div className="absolute inset-0 grain pointer-events-none" />
      <div className="text-center max-w-lg px-6 relative">
        <Sparkles size={32} className="mx-auto text-[color:var(--coral)] mb-8 animate-slow-pulse" />
        <div className="eyebrow mb-4">{t("createAlbum.composing")}</div>
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
          {stages[stage]}
        </p>
        <p className="text-sm text-[color:var(--muted)] mt-6">
          {t("createAlbum.composingNote")}
        </p>
      </div>
    </div>
  );
}

export default function CreateAlbum() {
  usePageMeta("create");
  const { t, i18n } = useTranslation();
  const STEPS = [t("createAlbum.steps.format"), t("createAlbum.steps.edit"), t("createAlbum.steps.pictures")];
  const [params] = useSearchParams();
  const resumeAlbumId = params.get("albumId");
  const chosenTemplate = findTemplate(params.get("template"));
  const [step, setStep] = useState(0);
  // Each step (cover, format, photos) starts at the top, like a new page.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [step]);
  const startFormat = templateFormat(params.get("template"));
  const [size, setSize] = useState(startFormat?.size || "A4");
  const [orientation, setOrientation] = useState(startFormat?.orientation || "portrait");
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
        toast.error(t("createAlbum.loadError"));
        nav("/dashboard");
      } finally {
        setResuming(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resumeAlbumId]);

  // A click anywhere outside the cover and its panel (or Escape) clears
  // the selection.
  const clearCoverSel = useCallback(() => setCoverSel(null), []);
  useDeselectOutside(step === 1 && !!coverSel, clearCoverSel);

  const template = getTemplate();
  const { updateCover, updateCoverTitle, updateAlbumTitle, updateCoverItem, addCoverText, addSpineText, addCoverShape, addCoverImage, removeCoverItem, clearSpineZone } =
    makeCoverEditingActions({ setAlbum, albumId: album?.id, coverSel, setCoverSel });

  // Same clipboard used by AlbumEditor.jsx's cover editing (Ctrl+C/Ctrl+V
  // duplicates the selected cover item) — kept here too so this earlier,
  // pre-creation cover-editing step behaves identically to the later one
  // instead of silently missing the shortcut.
  const clipboardRef = useRef(null);

  useEffect(() => {
    if (!coverSel) return;
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
  }, [coverSel]);

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
        return;
      }
      if (isMod && e.key.toLowerCase() === "c") {
        if (coverSel?.mode === "item") {
          const cover = album?.cover || {};
          const key = coverSel.side === "back" ? "back_extra_items" : "extra_items";
          const found = (cover[key] || []).find((it) => it.id === coverSel.itemId);
          if (found) clipboardRef.current = { side: coverSel.side, item: JSON.parse(JSON.stringify(found)) };
        }
        return;
      }
      if (isMod && e.key.toLowerCase() === "v") {
        const clip = clipboardRef.current;
        if (!clip) return;
        e.preventDefault();
        const newId = cryptoRandom();
        const offset = 0.03;
        const w = clip.item.w ?? 0.1;
        const h = clip.item.h ?? 0.1;
        const nx = Math.min((clip.item.x || 0) + offset, 1 - w);
        const ny = Math.min((clip.item.y || 0) + offset, 1 - h);
        const side = coverSel?.side || clip.side;
        const key = side === "back" ? "back_extra_items" : "extra_items";
        const newItem = { ...clip.item, id: newId, x: nx, y: ny };
        setAlbum((prev) => {
          const cover = prev.cover || {};
          return { ...prev, cover: { ...cover, [key]: [...(cover[key] || []), newItem] } };
        });
        setCoverSel({ mode: "item", side, itemId: newId });
        return;
      }
      if (e.key === "Delete" || e.key === "Backspace") {
        if (coverSel?.mode === "item") {
          e.preventDefault();
          removeCoverItem(coverSel.itemId, coverSel.side);
        } else if (coverSel?.mode === "title" || coverSel?.mode?.startsWith("spine-")) {
          e.preventDefault();
          clearSpineZone(coverSel.mode);
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [coverSel, album]);


  // Format -> Edit: create the album the first time, or persist size/orientation if we're revisiting.
  const goToEdit = async () => {
    setBusy(true);
    try {
      if (!album) {
        const { data } = await api.post("/albums", {
          size,
          orientation,
          target_pages: targetPages,
          title: chosenTemplate?.title || t("createAlbum.untitled"),
          cover_template_id: chosenTemplate?.id || "default",
          cover: defaultCoverPayload(chosenTemplate),
          lang: i18n.language?.startsWith("fr") ? "fr" : "en",
        });
        albumHistory.resetState(data);
      } else {
        await api.patch(`/albums/${album.id}`, { size, orientation, target_pages: targetPages });
      }
      setStep(1);
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("createAlbum.createError"));
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
      toast.error(t("createAlbum.saveError"));
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

  const mountedRef = useRef(true);
  useEffect(() => () => {
    mountedRef.current = false;
  }, []);

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
    const fail = (message) => {
      clearInterval(interval);
      toast.error(message || t("createAlbum.creationError"));
      setBusy(false);
      setCreationProgress(0);
    };
    let status;
    try {
      const { data } = await api.post(`/albums/${album.id}/process`);
      status = data?.status;
    } catch (err) {
      // No answer at all (connection dropped, timeout): the server may well
      // be composing the album anyway — follow it rather than give up.
      if (err?.response) return fail(err.response.data?.detail);
      status = "processing";
    }
    // The layout goes on on the server without this page: the page only
    // follows it, and a weak connection just delays the news.
    while (status === "processing") {
      await new Promise((resolve) => setTimeout(resolve, 2500));
      if (!mountedRef.current) return;
      try {
        const { data } = await api.get(`/albums/${album.id}/status`);
        status = data.status;
      } catch {
        /* connection lost for a moment: keep following */
      }
    }
    if (status !== "ready") return fail();
    clearInterval(interval);
    setCreationProgress(100);
    toast.success(t("createAlbum.composingToast"));
    setTimeout(() => nav(`/editor/${album.id}?processing=1`), 500);
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
    // Fonts tried out in a list aren't added to the undo history.
    <HistoryPreviewContext.Provider value={albumHistory.withoutHistory}>
    <main className="min-h-screen bg-[color:var(--paper)] pt-24 pb-24 px-6 md:px-12">
      <div className="max-w-[1400px] mx-auto">
        {/* Stepper */}
        {/* Tighter on a phone, where it ran past the screen's edge. */}
        <div className="flex items-center gap-2 sm:gap-4 mb-10 md:mb-14">
          {STEPS.map((s, i) => (
            <div key={i} className="flex items-center gap-2 sm:gap-4">
              <div
                className={`w-6 h-6 flex items-center justify-center text-[10px] font-semibold ${
                  i <= step ? "bg-[color:var(--ink)] text-[color:var(--paper)]" : "bg-[color:var(--editor-canvas)] text-[color:var(--muted)]"
                }`}
              >
                {i + 1}
              </div>
              <span className={`eyebrow ${i === step ? "text-[color:var(--ink)]" : "text-[color:var(--muted)]"}`}>{s}</span>
              {i < STEPS.length - 1 && <div className="w-3 sm:w-8 h-px bg-[color:var(--border-soft)]" />}
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
            addSpineText={addSpineText}
            updateCoverItem={updateCoverItem}
            addCoverText={addCoverText}
            addCoverShape={addCoverShape}
            addCoverImage={addCoverImage}
            removeCoverItem={removeCoverItem}
            history={albumHistory}
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
              <ArrowLeft size={16} /> {step === 0 ? t("createAlbum.cancel") : t("createAlbum.back")}
            </button>
            <button
              data-testid={TID.wizardNext}
              data-tour="wizard-continue"
              onClick={next}
              disabled={!canProceed() || busy}
              className="inline-flex items-center gap-3 bg-[color:var(--ink)] text-[color:var(--paper)] px-10 py-4 hover:bg-[color:var(--coral)] transition-colors disabled:opacity-40"
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : <span className="text-sm font-semibold tracking-widest uppercase">{t("createAlbum.continue")}</span>}
              {!busy && <ArrowRight size={16} />}
            </button>
          </div>
        )}
      </div>
    </main>
    </HistoryPreviewContext.Provider>
  );
}

// -------------------- STEP COMPONENTS --------------------



function StepFormat({ size, setSize, orientation, setOrientation, targetPages, setTargetPages }) {
  const { t, i18n } = useTranslation();
  // The page's real size, in cm (21 × 29.7 for an A4 portrait).
  const dims = pageDimsMm(size, orientation);
  // Plain formatting: Intl.NumberFormat throws on some browser language
  // tags (en-US@posix), which took the whole page down.
  const cm = (mm) => {
    const value = String(Math.round(mm) / 10);
    return i18n.language?.startsWith("fr") ? value.replace(".", ",") : value;
  };
  const getAspectClass = () => (orientation === "landscape" ? "aspect-[1.414/1]" : "aspect-[1/1.414]");
  // A3 was removed — the printing office's max open (flat) size for a
  // hardcover is 70×33cm, and A3 exceeds that in both orientations
  // (portrait: 42cm open height, over the 33cm cap; landscape: 84cm open
  // width, well over the 70cm cap) — see the size/hardcover-limit analysis
  // this came from. A4 and A5 both stay comfortably within it.
  const maxWidthBySize = { A4: 500, A5: 400 };
  const sizeContainerStyle = {
    maxWidth: `${orientation === "landscape" ? maxWidthBySize[size] : maxWidthBySize[size] * 0.72}px`,
  };

  return (
    // Phone: the size and orientation choices beside the preview (not one
    // under the other), the page count below them. From tablet width: the
    // choices on the left, the preview on the right.
    <section className="animate-fade-up grid grid-cols-2 gap-x-4 gap-y-8 md:gap-x-16 md:gap-y-10">
      <div className="col-span-2 md:col-span-1 md:col-start-1">
        <h2 className="font-serif-display text-4xl md:text-5xl tracking-tight mb-3">{t("createAlbum.format.title")}</h2>
        <p className="text-[color:var(--ink)]/70">{t("createAlbum.format.subtitle")}</p>
      </div>
      <div className="col-start-1 min-w-0">
        <div className="mb-8 md:mb-10">
          <div className="eyebrow mb-4">{t("createAlbum.format.size")}</div>
          <div className="flex flex-wrap gap-2 md:gap-3">
            {["A4", "A5"].map((s) => (
              <button
                key={s}
                data-testid={TID.sizeOption}
                data-size={s}
                onClick={() => setSize(s)}
                className={`px-4 md:px-6 py-3 border ${
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
          <div className="eyebrow mb-4">{t("createAlbum.format.orientation")}</div>
          <div className="flex flex-wrap gap-2 md:gap-3">
            {[
              { v: "portrait", l: t("createAlbum.format.portrait") },
              { v: "landscape", l: t("createAlbum.format.landscape") },
            ].map((o) => (
              <button
                key={o.v}
                data-testid={TID.orientationOption}
                data-orientation={o.v}
                onClick={() => setOrientation(o.v)}
                className={`px-3 md:px-6 py-3 border ${
                  orientation === o.v
                    ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
                    : "border-[color:var(--ink)]/30 text-[color:var(--ink)] hover:border-[color:var(--ink)]"
                } transition-colors`}
              >
                <span className="font-semibold tracking-wider md:tracking-widest text-xs md:text-sm">{o.l}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="col-span-2 md:col-span-1 md:col-start-1">
        <div>
          <div className="eyebrow mb-4">{t("createAlbum.format.pageCount")}</div>
          <div className="flex flex-wrap gap-3">
            {PAGE_TIERS.map((tier) => (
              <button
                key={tier}
                onClick={() => setTargetPages(tier)}
                className={`px-6 py-3 border ${
                  targetPages === tier
                    ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
                    : "border-[color:var(--ink)]/30 text-[color:var(--ink)] hover:border-[color:var(--ink)]"
                } transition-colors`}
              >
                <span className="font-semibold tracking-widest text-sm block">{tier}p</span>
                <span className={`text-xs block mt-0.5 ${targetPages === tier ? "text-[color:var(--paper)]/70" : "text-[color:var(--ink)]/50"}`}>
                  ${computeUnitPrice(size, tier)}
                </span>
              </button>
            ))}
          </div>
          <p className="text-sm text-[color:var(--ink)]/70 mt-5">
            {size} · {t("createAlbum.format.pagesCount", { count: targetPages })}: <span className="font-semibold text-[color:var(--ink)]">${computeUnitPrice(size, targetPages)}</span>
            <span className="text-[color:var(--ink)]/50"> {t("createAlbum.format.perCopy")}</span>
            {/* The PDF version is chosen at checkout; it's told here already. */}
            <span className="block text-[color:var(--ink)]/60 mt-1" data-testid="format-pdf-price">
              {t("createAlbum.format.pdfPrice", { price: computeDigitalPrice(size, targetPages) })}
            </span>
          </p>
        </div>
      </div>
      <div className="col-start-2 row-start-2 md:row-start-1 md:row-span-3 flex items-center justify-center min-w-0">
        <div className="bg-[color:var(--editor-canvas)] p-3 md:p-8 transition-all duration-300 flex items-center justify-center w-full">
          <div className="w-full" style={sizeContainerStyle} data-testid="format-preview">
            {/* Width above the page, height beside it — the page's real size. */}
            <div className="flex items-center gap-1.5 mb-1.5 pr-[22px] md:pr-[26px] text-[10px] md:text-xs text-[color:var(--ink)]/60 whitespace-nowrap">
              <span className="h-px flex-1 bg-current opacity-50" />
              {cm(dims.w)} cm
              <span className="h-px flex-1 bg-current opacity-50" />
            </div>
            <div className="flex items-stretch gap-1.5">
              <div
                className={`${getAspectClass()} flex-1 min-w-0 relative transition-all duration-300 shadow-sm border border-[color:var(--border-soft)]`}
                style={{ background: "#E4E1D8" }}
              >
                <div className="absolute inset-0 grain" />
                <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-1">
                  <span className="font-serif-display text-base md:text-2xl text-[color:var(--ink)]/60">
                    {size} · {orientation === "landscape" ? t("createAlbum.format.landscapeLower") : t("createAlbum.format.portraitLower")}
                  </span>
                  <span className="mt-1 text-[10px] md:text-sm text-[color:var(--ink)]/50" data-testid="format-dimensions">
                    {cm(dims.w)} × {cm(dims.h)} cm
                  </span>
                </div>
              </div>
              <div className="w-4 md:w-5 flex flex-col items-center gap-1.5 text-[10px] md:text-xs text-[color:var(--ink)]/60">
                <span className="w-px flex-1 bg-current opacity-50" />
                <span className="whitespace-nowrap" style={{ writingMode: "vertical-rl" }}>{cm(dims.h)} cm</span>
                <span className="w-px flex-1 bg-current opacity-50" />
              </div>
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
  addSpineText,
  updateCoverItem,
  addCoverText,
  addCoverShape,
  addCoverImage,
  removeCoverItem,
  history,
}) {
  const { t } = useTranslation();
  const cover = album.cover || {};
  // Step-by-step guide to the cover, opened by itself the first time.
  const tour = useGuidedTour({
    id: "cover",
    prefix: "tour.cover",
    steps: COVER_TOUR,
    autoStart: true,
    context: { selectTitle: () => setCoverSel({ mode: "title", side: "front" }) },
  });
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
    <section className="animate-fade-up">
      {/* Title above both columns, so the panel starts level with the cover. */}
      <div className="mb-8 max-w-2xl">
        <div className="flex items-start justify-between gap-4">
          <h2 className="font-serif-display text-4xl md:text-5xl tracking-tight mb-3">{t("createAlbum.edit.title")}</h2>
          <div className="shrink-0 mt-2 flex items-center gap-2">
            <HistoryButton icon={<Undo2 size={14} />} label={t("createAlbum.edit.undo")} title={t("albumEditor.undoTitle")} onClick={history.undo} disabled={!history.canUndo()} tid="cover-undo" />
            <HistoryButton icon={<Redo2 size={14} />} label={t("createAlbum.edit.redo")} title={t("albumEditor.redoTitle")} onClick={history.redo} disabled={!history.canRedo()} tid="cover-redo" />
            <TourHelpButton onClick={tour.start} />
          </div>
        </div>
        <p className="text-[color:var(--ink)]/70">
          {t("createAlbum.edit.subtitle")}
        </p>
      </div>
      {/* Panel beside the cover from tablet/small-laptop width up (narrower
          there), under it only on phones. */}
      <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_260px] lg:grid-cols-[minmax(0,1fr)_320px] gap-6 lg:gap-10 items-start">
        <div
          data-tour="cover-spread"
          className="grid w-full gap-[3px] rounded-sm overflow-hidden book-shadow max-w-3xl mx-auto bg-[color:var(--ink)]/70"
          style={{ gridTemplateColumns: `1fr ${spineFr}fr 1fr` }}
        >
          <CoverBackPage
            template={template}
            country={album.country}
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
            templateId={album.cover_template_id}
            template={template}
            cover={cover}
            editable
            selectedZone={coverSel?.mode}
            onSelectTitle={() => setCoverSel({ mode: "spine-title" })}
            onSelectSubtitle={() => setCoverSel({ mode: "spine-subtitle" })}
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
            templateId={album.cover_template_id}
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
        <div data-tour="cover-panel" className="md:sticky md:top-20">
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
              addSpineText={addSpineText}
              onDismiss={() => setCoverSel(null)}
            />
          ) : (
            <div className="text-sm text-[color:var(--muted)] border border-dashed border-[color:var(--border-soft)] p-6">
              {t("createAlbum.edit.hint")}
            </div>
          )}
        </div>
      </div>
      {tour.element}
    </section>
  );
}

// Undo / redo on the cover step (same history as Ctrl+Z / Ctrl+Y).
function HistoryButton({ icon, label, title, onClick, disabled, tid }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={label}
      data-testid={tid}
      className="inline-flex items-center gap-1.5 border border-[color:var(--ink)]/20 px-3 py-1.5 text-xs font-semibold tracking-widest uppercase text-[color:var(--ink)]/70 hover:border-[color:var(--ink)] hover:text-[color:var(--ink)] transition-colors disabled:opacity-40 disabled:pointer-events-none"
    >
      {icon}
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}

// The absolute floor: since the layout always uses at least 1 photo per
// page, filling `targetPages` pages is mathematically impossible with
// fewer than this many photos, no matter how good they are.
function minimumRequiredPhotos(targetPages) {
  return Math.max(0, (targetPages || 0) - 1);
}

function StepPhotos({ albumId, serverPhotos, onServerPhotosChange, targetPages, onBack, onCreate, canCreate, busy }) {
  const { t } = useTranslation();
  const minimum = minimumRequiredPhotos(targetPages);
  const uploaded = serverPhotos.length;
  const belowMinimum = uploaded < minimum;
  const [importing, setImporting] = useState(false);

  return (
    <section className="animate-fade-up">
      <h2 className="font-serif-display text-4xl md:text-5xl tracking-tight mb-3">{t("createAlbum.photos.title")}</h2>
      <p className="text-[color:var(--ink)]/70 mb-4">
        {t("createAlbum.photos.subtitle")}
      </p>

      {/* Before the first photo: just how many are needed. Then a count
          with a progress bar, until the minimum is reached. */}
      {uploaded === 0 ? (
        <div className="text-sm border rounded px-4 py-3 mb-6 text-[color:var(--ink)]/80 bg-[color:var(--editor-canvas)] border-[color:var(--border-soft)]" data-testid="photos-minimum">
          {t("createAlbum.photos.howMany", { minimum, targetPages })}
        </div>
      ) : (
        <div
          data-testid="photos-minimum"
          className={`text-sm border rounded px-4 py-3 mb-6 ${
            belowMinimum
              ? "text-[color:var(--ink)]/80 bg-[color:var(--editor-canvas)] border-[color:var(--border-soft)]"
              : "text-emerald-700 bg-emerald-50 border-emerald-200"
          }`}
        >
          {belowMinimum
            ? t("createAlbum.photos.belowMinimum", { count: uploaded, minimum, remaining: minimum - uploaded })
            : t("createAlbum.photos.aboveMinimum", { count: uploaded })}
          {belowMinimum && (
            <div className="mt-2 h-1.5 bg-[color:var(--ink)]/10 rounded-full overflow-hidden">
              <div
                className="h-full bg-[color:var(--coral)] transition-all"
                style={{ width: `${Math.min(100, (uploaded / Math.max(1, minimum)) * 100)}%` }}
              />
            </div>
          )}
        </div>
      )}

      <PhotoUploadMethods
        albumId={albumId}
        mode="wizard"
        photos={serverPhotos}
        onPhotosChange={onServerPhotosChange}
        onImportingChange={setImporting}
        afterMethodsRow={
          <div className="my-6 flex items-center justify-between border-y border-[color:var(--border-soft)] py-4">
            <button
              onClick={onBack}
              className="inline-flex items-center gap-3 text-sm font-semibold tracking-widest uppercase text-[color:var(--muted)] hover:text-[color:var(--ink)] transition-colors"
            >
              <ArrowLeft size={16} /> {t("createAlbum.back")}
            </button>
            <button
              onClick={onCreate}
              disabled={!canCreate || busy || importing}
              title={importing ? t("createAlbum.photos.waitForImport") : undefined}
              className="inline-flex items-center gap-3 bg-[color:var(--coral)] text-[color:var(--paper)] px-10 py-4 hover:bg-[color:var(--ink)] transition-colors disabled:opacity-60"
            >
              {busy || importing ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
              <span className="text-sm font-semibold tracking-widest uppercase">{importing ? t("createAlbum.photos.importing") : t("createAlbum.photos.createAlbum")}</span>
            </button>
          </div>
        }
      />
    </section>
  );
}
