import React, { useEffect, useState, useRef, useCallback, useMemo } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, coverImageUrl } from "@/lib/api";
import { toast } from "sonner";
import { getTemplate } from "@/lib/coverTemplates";
import { CoverEditorPanel } from "@/components/CoverEditorPanel";
import { makeCoverEditingActions, computeAlignSnap, computeResizeAlignSnap } from "@/lib/coverEditing";
import { LAYOUT_PATTERNS } from "@/lib/layoutPatterns";
import { useHistoryState } from "@/lib/useHistoryState";
import PhotoTray from "@/components/PhotoTray";
import PhotoGallery from "@/components/PhotoGallery";
import PhotoUploadMethods from "@/components/PhotoUploadMethods";
import { TID } from "@/constants/testIds";
import { ChevronLeft, ChevronRight, ShoppingBag, Save, Type, Loader2, Undo2, Redo2, Plus } from "lucide-react";
import { BookRenderer } from "@/components/editor/BookRenderer";
import { ProcessingScreen } from "@/components/editor/ProcessingScreen";
import { RepackPagesForm } from "@/components/editor/RepackPagesForm";
import { spreadNumberToPageCount } from "@/components/editor/spreads";
import { cryptoRandom } from "@/lib/cryptoRandom";
import { fitItemToPhoto } from "@/lib/photoFit";

export default function AlbumEditor() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const { t } = useTranslation();

  // --- États de l'Éditeur ---
  const bookRef = useRef();
  const [album, setAlbum, albumHistory] = useHistoryState(null);
  const [showRepackForm, setShowRepackForm] = useState(false);
  const [repacking, setRepacking] = useState(false);
  const albumRef = useRef(null);
  useEffect(() => {
    albumRef.current = album;
  }, [album]);
  // "All your photos" is otherwise in raw upload order — sorted here the
  // same way the AI's own curation prioritizes: taken_at when a photo has
  // one (undated photos pushed to the end, in their original relative
  // order, rather than scattered throughout). This mirrors the AI's
  // chronological ordering for browsing purposes; it doesn't replicate its
  // fuller location-clustering logic, which is really about how photos
  // land on album PAGES, not about sorting a flat browsing list.
  const sortedAlbumPhotos = useMemo(() => {
    const photos = album?.photos || [];
    return [...photos].sort((a, b) => {
      if (a.taken_at && b.taken_at) return new Date(a.taken_at) - new Date(b.taken_at);
      if (a.taken_at) return -1;
      if (b.taken_at) return 1;
      return 0;
    });
  }, [album?.photos]);
  const [pageIndex, setPageIndex] = useState(0);
  const [selected, setSelected] = useState(null);
  const [cropMode, setCropMode] = useState(false);
  const [saving, setSaving] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState(null);
  const [processing, setProcessing] = useState(params.get("processing") === "1");
  const [coverSel, setCoverSel] = useState(null);
  const clipboardRef = useRef(null);
  // Guards against the "Album prêt" toast appearing more than once for the
  // same processing run (e.g. React re-invoking effects, or the status
  // poll landing twice before the interval is torn down).
  const notifiedRef = useRef(false);

  const loadAlbum = useCallback(async () => {
    try {
      const { data } = await api.get(`/albums/${id}`);
      albumHistory.resetState(data);
      if (data.status === "processing") {
        notifiedRef.current = false;
        setProcessing(true);
      } else setProcessing(false);
    } catch {
      toast.error(t("albumEditor.loadError"));
      nav("/dashboard");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, nav]);

  useEffect(() => {
    loadAlbum();
  }, [loadAlbum]);

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
        if (selected) {
          clipboardRef.current = { scope: "page", pageIdx: selected.pageIdx, item: JSON.parse(JSON.stringify(selected.item)) };
        } else if (coverSel?.mode === "item") {
          const cover = albumRef.current?.cover || {};
          const key = coverSel.side === "back" ? "back_extra_items" : "extra_items";
          const found = (cover[key] || []).find((it) => it.id === coverSel.itemId);
          if (found) clipboardRef.current = { scope: "cover", side: coverSel.side, item: JSON.parse(JSON.stringify(found)) };
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
        if (clip.scope === "page") {
          const targetPageIdx = selected ? selected.pageIdx : clip.pageIdx;
          const newItem = { ...clip.item, id: newId, x: nx, y: ny };
          setAlbum((prev) => {
            const newPages = [...prev.pages];
            newPages[targetPageIdx] = { ...newPages[targetPageIdx], items: [...newPages[targetPageIdx].items, newItem] };
            return { ...prev, pages: newPages };
          });
          setSelected({ pageIdx: targetPageIdx, item: newItem });
        } else if (clip.scope === "cover") {
          const side = coverSel?.side || clip.side;
          const key = side === "back" ? "back_extra_items" : "extra_items";
          const newItem = { ...clip.item, id: newId, x: nx, y: ny };
          setAlbum((prev) => {
            const cover = prev.cover || {};
            return { ...prev, cover: { ...cover, [key]: [...(cover[key] || []), newItem] } };
          });
          setCoverSel({ mode: "item", side, itemId: newId });
        }
        return;
      }
      if (e.key === "Delete" || e.key === "Backspace") {
        if (selected) {
          e.preventDefault();
          removeSelected();
        } else if (coverSel?.mode === "item") {
          e.preventDefault();
          removeCoverItem(coverSel.itemId, coverSel.side);
        } else if (coverSel?.mode?.startsWith("spine-")) {
          e.preventDefault();
          clearSpineZone(coverSel.mode);
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, coverSel]);

  useEffect(() => {
    if (!processing) return;
    const interval = setInterval(async () => {
      try {
        const { data } = await api.get(`/albums/${id}/status`);
        if (data.status !== "processing") {
          setProcessing(false);
          loadAlbum();
          if (!notifiedRef.current) {
            notifiedRef.current = true;
            if (data.status === "ready") toast.success(t("albumEditor.readyToast"));
            if (data.status === "error") toast.error(t("albumEditor.aiError"));
          }
        }
      } catch {
        /* noop */
      }
    }, 2500);
    return () => clearInterval(interval);
  }, [processing, id, loadAlbum]);

  const save = async (opts = {}) => {
    const { silent = false } = opts;
    const current = albumRef.current;
    if (!current) return;
    setSaving(true);
    try {
      await api.patch(`/albums/${id}`, { title: current.title, country: current.country, year: current.year, pages: current.pages, cover: current.cover || {} });
      setLastSavedAt(new Date());
      if (!silent) toast.success(t("common.saved"));
      return true;
    } catch (err) {
      toast.error(err?.response?.status === 403 ? t("albumEditor.lockedError") : t("albumEditor.saveError"));
      return false;
    } finally {
      setSaving(false);
    }
  };

  // Auto-save every 2 minutes so "My Albums" always reflects recent edits,
  // even if the user never clicks the Save button themselves — silent, so it
  // never interrupts with a popup; a small "Saved automatically" note near
  // the Save button is enough.
  useEffect(() => {
    if (!album) return;
    const interval = setInterval(() => {
      save({ silent: true });
    }, 2 * 60 * 1000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [album?.id]);

  const goToOrder = async () => {
    // Auto-save only runs every 2 minutes (or on a manual Save click) —
    // without an explicit save here, a page deletion (or any other edit)
    // made right before clicking "Order Album" was still sitting only in
    // this component's local state, never sent to the server. The order
    // page then fetched "fresh" data that was genuinely still the old,
    // pre-edit version, since the edit itself had never been saved yet —
    // showing as a stale page count that never seemed to update.
    // The PDF is made from the saved album: never go on to the order with
    // edits that didn't reach the server.
    if (!(await save({ silent: true }))) return;
    nav(`/order/${id}`);
  };

  const updateItemById = (pageIdx, itemId, patch) => {
    setAlbum((prev) => {
      if (!prev) return prev;
      const newPages = [...prev.pages];
      const pageItems = newPages[pageIdx].items;
      const siblings = pageItems.filter((it) => it.id !== itemId);
      let guideX = null, guideY = null;
      const items = pageItems.map((it) => {
        if (it.id !== itemId) return it;
        const updatedPatch = { ...patch };
        const currentW = updatedPatch.w ?? it.w ?? 0;
        const currentH = updatedPatch.h ?? it.h ?? 0;
        if (updatedPatch.x !== undefined) {
          const s = computeAlignSnap(updatedPatch.x, currentW, siblings, "x");
          updatedPatch.x = s.value;
          guideX = s.guide;
        }
        if (updatedPatch.y !== undefined) {
          const s = computeAlignSnap(updatedPatch.y, currentH, siblings, "y");
          updatedPatch.y = s.value;
          guideY = s.guide;
        }
        // Resizing (dragging the corner handle) only ever changes w/h, not
        // x/y — the item's top-left corner stays put, so this checks
        // whether the *moving* edge (x+w or y+h) lines up with a sibling's
        // edge/center instead, using the same guide-line mechanism as a
        // move.
        if (updatedPatch.w !== undefined && updatedPatch.x === undefined) {
          const s = computeResizeAlignSnap(it.x ?? 0, updatedPatch.w, siblings, "x");
          updatedPatch.w = s.value;
          guideX = s.guide;
        }
        if (updatedPatch.h !== undefined && updatedPatch.y === undefined) {
          const s = computeResizeAlignSnap(it.y ?? 0, updatedPatch.h, siblings, "y");
          updatedPatch.h = s.value;
          guideY = s.guide;
        }
        if (it.type === "photo" && it.slot && patch.slot === undefined) {
          const moved = { ...it, ...updatedPatch };
          if (updatedPatch.w !== undefined || updatedPatch.h !== undefined) {
            // Resized by hand: the new frame becomes its area.
            updatedPatch.slot = { x: moved.x, y: moved.y, w: moved.w, h: moved.h };
          } else if (updatedPatch.x !== undefined || updatedPatch.y !== undefined) {
            // Moved: the area follows.
            updatedPatch.slot = { ...it.slot, x: it.slot.x + (moved.x - it.x), y: it.slot.y + (moved.y - it.y) };
          }
        }
        return { ...it, ...updatedPatch };
      });
      newPages[pageIdx] = { ...newPages[pageIdx], items, align_guide_x: guideX, align_guide_y: guideY };
      return { ...prev, pages: newPages };
    });
    setSelected((prev) => (prev && prev.item?.id === itemId ? { ...prev, item: { ...prev.item, ...patch } } : prev));
  };

  const { updateCover, updateCoverTitle, updateAlbumTitle, updateCoverItem, addCoverText, addSpineText, addCoverShape, addCoverImage, removeCoverItem, clearSpineZone } =
    makeCoverEditingActions({ setAlbum, albumId: id, coverSel, setCoverSel });

  const deleteItemById = (pageIdx, itemId) => {
    setAlbum((prev) => {
      if (!prev) return prev;
      const newPages = [...prev.pages];
      newPages[pageIdx] = {
        ...newPages[pageIdx],
        items: newPages[pageIdx].items.filter((it) => it.id !== itemId),
      };
      return { ...prev, pages: newPages };
    });
    setSelected((prev) => (prev && prev.item?.id === itemId ? null : prev));
    setCropMode(false);
  };

  const swapItemsAcrossPages = (srcPageIdx, srcItemId, tgtPageIdx, tgtItemId) => {
    setAlbum((prev) => {
      if (!prev) return prev;
      const newPages = [...prev.pages];
      const srcItems = newPages[srcPageIdx].items;
      const tgtItems = srcPageIdx === tgtPageIdx ? srcItems : newPages[tgtPageIdx].items;
      const a = srcItems.find((it) => it.id === srcItemId);
      const b = tgtItems.find((it) => it.id === tgtItemId);
      if (!a || !b) return prev;
      const photoOf = (photoId) => prev.photos?.find((p) => p.id === photoId);
      const swapFields = (it, other) => ({
        ...it,
        ...fitItemToPhoto(it, photoOf(other.photo_id), prev.orientation),
        photo_id: other.photo_id,
        focal_x: other.focal_x,
        focal_y: other.focal_y,
        scale: other.scale,
        rotation: other.rotation,
      });
      if (srcPageIdx === tgtPageIdx) {
        newPages[srcPageIdx] = {
          ...newPages[srcPageIdx],
          items: srcItems.map((it) => {
            if (it.id === srcItemId) return swapFields(it, b);
            if (it.id === tgtItemId) return swapFields(it, a);
            return it;
          }),
        };
      } else {
        newPages[srcPageIdx] = { ...newPages[srcPageIdx], items: srcItems.map((it) => (it.id === srcItemId ? swapFields(it, b) : it)) };
        newPages[tgtPageIdx] = { ...newPages[tgtPageIdx], items: tgtItems.map((it) => (it.id === tgtItemId ? swapFields(it, a) : it)) };
      }
      return { ...prev, pages: newPages };
    });
    toast.success(t("albumEditor.picturesSwapped"));
  };

  // Global so a swap can be started on one page and completed on another —
  // click "Swap" (or double-click a photo) to mark it as the source, then
  // click any other photo anywhere in the book to complete the swap.
  const [swapSource, setSwapSource] = useState(null); // { pageIdx, itemId } | null
  const [placingPhotoId, setPlacingPhotoId] = useState(null); // gallery photo armed for click-to-place

  const handleSwapAction = (pageIdx, itemId) => {
    if (itemId === null) {
      setSwapSource(null);
      return;
    }
    if (!swapSource) {
      setSwapSource({ pageIdx, itemId });
      return;
    }
    if (swapSource.pageIdx === pageIdx && swapSource.itemId === itemId) {
      setSwapSource(null); // clicked the same photo again — cancel
      return;
    }
    swapItemsAcrossPages(swapSource.pageIdx, swapSource.itemId, pageIdx, itemId);
    setSwapSource(null);
  };

  // Moves an item one step forward (toward the top) or backward (toward
  // the bottom) in the stacking order — items later in the array render on
  // top of earlier ones.
  const reorderItemLayer = (pageIdx, itemId, direction) => {
    setAlbum((prev) => {
      if (!prev) return prev;
      const items = [...prev.pages[pageIdx].items];
      const idx = items.findIndex((it) => it.id === itemId);
      if (idx === -1) return prev;
      const newIdx = direction === "forward" ? Math.min(idx + 1, items.length - 1) : Math.max(idx - 1, 0);
      if (newIdx === idx) return prev;
      const [moved] = items.splice(idx, 1);
      items.splice(newIdx, 0, moved);
      const newPages = [...prev.pages];
      newPages[pageIdx] = { ...newPages[pageIdx], items };
      return { ...prev, pages: newPages };
    });
  };

  // Reflows a page onto the chosen layout: existing photos (their content —
  // photo, zoom, focal point, rotation) move into the new pattern's slots in
  // order, and any extra slots the pattern needs become empty frames. If the
  // page already has more photos than the pattern has slots, the extra ones
  // are left exactly where they were rather than dropped.
  // Removes a whole page — any photos placed on it simply become
  // unplaced again (they're still part of the curated set and reappear in
  // "All your photos" below, since that gallery derives what's "placed"
  // from album.pages at render time; nothing extra to clean up there).
  // Page 0 (the very first interior page) isn't specially protected here —
  // any interior page can go, since the actual cover/title lives in its
  // own separate CoverFrontPage, not in this array.
  const deletePage = (pageIdx) => {
    setAlbum((prev) => {
      if (!prev) return prev;
      const newPages = prev.pages.filter((_, i) => i !== pageIdx);
      return { ...prev, pages: newPages };
    });
    setSelected(null);
  };

  // Appends one new, empty page (a single photo slot, ready to drag a
  // photo from "All your photos" onto) — for when album.pages is shorter
  // than the page count the person actually chose and paid for (e.g. after
  // deleting some, or if the AI fell short — see pages_below_target).
  const addBlankPage = () => {
    setAlbum((prev) => {
      if (!prev) return prev;
      const slot = LAYOUT_PATTERNS.single_full.slots[0];
      const newPage = {
        id: cryptoRandom(),
        layout: "single_full",
        items: [
          {
            id: cryptoRandom(),
            type: "photo",
            photo_id: null,
            focal_x: 0.5,
            focal_y: 0.5,
            scale: 1,
            rotation: 0,
            ...slot,
          },
        ],
      };
      // Inserted right after whichever double-page spread is currently
      // showing (same "Double-page N" → pages-array-index math used by
      // "Change total page count" below), rather than always tacked onto
      // the very end — so it lands right where the person's actually
      // looking, not somewhere they have to go hunt for afterward.
      const insertAt = Math.min(prev.pages.length, spreadNumberToPageCount(pageIndex + 1));
      const newPages = [...prev.pages.slice(0, insertAt), newPage, ...prev.pages.slice(insertAt)];
      return { ...prev, pages: newPages };
    });
  };

  // Changes the album's total page count after the fact (e.g. 150 → 100)
  // without re-running curation — the backend re-flows every photo already
  // on the pages being touched into a denser or sparser layout, keeping
  // the first `keepFirstPages` pages (title page, plus anything already
  // hand-edited) completely untouched.
  const handleRepackPages = async ({ targetPages, keepFirstPages }) => {
    if (!album) return;
    setRepacking(true);
    try {
      const { data } = await api.post(`/albums/${album.id}/repack-pages`, {
        target_pages: targetPages,
        keep_first_pages: keepFirstPages,
      });
      toast.success(t("albumEditor.resizedToast", { count: data.pages }));
      setShowRepackForm(false);
      await loadAlbum();
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("albumEditor.resizeError"));
    } finally {
      setRepacking(false);
    }
  };

  const applyLayoutToPage = (pageIdx, patternName) => {
    const pattern = LAYOUT_PATTERNS[patternName];
    if (!pattern) return;
    setAlbum((prev) => {
      if (!prev) return prev;
      const existingItems = prev.pages[pageIdx].items || [];
      const existingPhotos = existingItems.filter((it) => it.type === "photo");
      const otherItems = existingItems.filter((it) => it.type !== "photo");
      const reflowedPhotos = pattern.slots.map((slot, i) => {
        const existing = existingPhotos[i];
        if (existing) {
          const photo = prev.photos?.find((p) => p.id === existing.photo_id);
          return { ...existing, ...fitItemToPhoto({ ...existing, slot }, photo, prev.orientation) };
        }
        return {
          slot,
          id: cryptoRandom(),
          type: "photo",
          photo_id: null,
          focal_x: 0.5,
          focal_y: 0.5,
          scale: 1,
          rotation: 0,
          ...slot,
        };
      });
      const leftoverPhotos = existingPhotos.slice(pattern.slots.length); // kept untouched if the new layout has fewer slots
      const newPages = [...prev.pages];
      newPages[pageIdx] = { ...newPages[pageIdx], items: [...reflowedPhotos, ...leftoverPhotos, ...otherItems] };
      return { ...prev, pages: newPages };
    });
  };

  const replacePhotoInItem = (pageIdx, itemId, photoId) => {
    setAlbum((prev) => {
      if (!prev) return prev;
      const newPages = [...prev.pages];
      newPages[pageIdx] = {
        ...newPages[pageIdx],
        items: newPages[pageIdx].items.map((it) =>
          it.id === itemId
            ? {
                ...it,
                ...fitItemToPhoto(it, prev.photos?.find((p) => p.id === photoId), prev.orientation),
                photo_id: photoId,
                focal_x: 0.5,
                focal_y: 0.5,
                scale: 1,
              }
            : it
        ),
      };
      return { ...prev, pages: newPages };
    });
  };

  const addPhotoAt = (pageIdx, photoId, box) => {
    const photo = album?.photos?.find((p) => p.id === photoId);
    const newItem = {
      id: cryptoRandom(),
      type: "photo",
      photo_id: photoId,
      focal_x: 0.5,
      focal_y: 0.5,
      scale: 1,
      ...fitItemToPhoto(box, photo, album?.orientation),
    };
    setAlbum((prev) => {
      if (!prev) return prev;
      const newPages = [...prev.pages];
      newPages[pageIdx] = { ...newPages[pageIdx], items: [...newPages[pageIdx].items, newItem] };
      return { ...prev, pages: newPages };
    });
    setSelected({ pageIdx, item: newItem });
    toast.success(t("albumEditor.pictureAdded"));
  };

  const [placingText, setPlacingText] = useState(false);
  const [autoEditItemId, setAutoEditItemId] = useState(null);

  const placeTextAt = (pageIdx, box) => {
    const newItem = {
      id: cryptoRandom(),
      type: "text",
      content: t("albumEditor.yourCaption"),
      x: box.x,
      y: box.y,
      w: 0.5,
      h: 0.08,
      font: "'Cormorant Garamond', serif",
      color: "#1A1A17",
      font_size: 24,
    };
    setAlbum((prev) => {
      const newPages = [...prev.pages];
      newPages[pageIdx] = { ...newPages[pageIdx], items: [...newPages[pageIdx].items, newItem] };
      return { ...prev, pages: newPages };
    });
    setSelected({ pageIdx, item: newItem });
    setPlacingText(false);
    setAutoEditItemId(newItem.id);
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
  // RENDU : ÉCRAN DE CHARGEMENT DE L'IA
  // ==========================================
  if (!album) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[color:var(--editor-canvas)]">
        <p className="eyebrow animate-slow-pulse">{t("albumEditor.loadingAlbum")}</p>
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
    <main className="min-h-screen bg-[color:var(--editor-canvas)] pt-16 pb-16 relative">
      <div className="absolute inset-0 grain pointer-events-none" />

      <div className="max-w-[1600px] mx-auto px-4 md:px-8 grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6 items-start">
        {/* Zone du Livre */}
        <div className="flex flex-col items-center pt-2">
          <div className="w-full max-w-2xl mb-4 flex items-center justify-between">
            <h1 className="font-serif-display text-2xl truncate">{album.title}</h1>
            <div />
          </div>
          {album.was_ordered && (
            <div className="w-full max-w-2xl mb-4 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
              {t("albumEditor.orderedBanner")}
            </div>
          )}
          <div className="w-full max-w-2xl mb-4 text-xs text-[color:var(--muted)] bg-[color:var(--editor-canvas)] border border-[color:var(--border-soft)] rounded px-3 py-2">
            {t("albumEditor.previewQualityNote")}
          </div>

          <BookRenderer
            album={album}
            template={albumTemplate}
            orientation={albumOrientation}
            bookRef={bookRef}
            onSelectItem={(pageIdx, item) => {
              setSelected(item ? { pageIdx, item } : null);
              setCropMode(false);
              setCoverSel(null);
            }}
            onUpdateItem={updateItemById}
            onDeleteItem={deleteItemById}
            swapSourceItemId={swapSource?.itemId}
            onSwapAction={handleSwapAction}
            onAddPhotoAt={addPhotoAt}
            onReplacePhoto={replacePhotoInItem}
            onReorderLayer={reorderItemLayer}
            onApplyLayout={applyLayoutToPage}
            onDeletePage={deletePage}
            placingPhotoId={placingPhotoId}
            onPhotoPlaced={() => setPlacingPhotoId(null)}
            selectedId={selected?.item?.id}
            cropMode={cropMode}
            onEnterCrop={(itemId) => setCropMode(true)}
            onExitCrop={() => setCropMode(false)}
            placingText={placingText}
            onPlaceText={placeTextAt}
            onStartAddText={() => setPlacingText(true)}
            autoEditItemId={autoEditItemId}
            onTextEditHandled={() => setAutoEditItemId(null)}
            onFlip={(p) => {
              setPageIndex(p);
              if (p !== 0) setCoverSel(null);
            }}
            coverImageUrl={album.cover_image_path ? coverImageUrl(id, 0) : null}
            coverSel={coverSel}
            onSelectCover={(side = "front") => { setSelected(null); setCoverSel({ mode: "cover", side }); }}
            onSelectCoverTitle={() => { setSelected(null); setCoverSel({ mode: "title", side: "front" }); }}
            onSelectCoverItem={(item, side = "front") => { setSelected(null); setCoverSel({ mode: "item", side, itemId: item.id }); }}
            onUpdateCoverTitle={updateCoverTitle}
            onUpdateCoverItem={updateCoverItem}
            onUpdateCover={updateCover}
            onSelectSpine={(mode) => { setSelected(null); setCoverSel({ mode }); }}
          />

          <div className="flex items-center gap-4 mt-4">
            <button
              data-testid={TID.editorPrev}
              onClick={() => bookRef.current?.pageFlip()?.flipPrev()}
              className="p-3 border border-[color:var(--ink)]/20 hover:bg-white transition-colors"
              aria-label={t("albumEditor.previousPage")}
            >
              <ChevronLeft size={16} />
            </button>
            <span className="eyebrow">{t("albumEditor.doublePage", { count: pageIndex + 1 })}</span>
            <button
              data-testid={TID.editorNext}
              onClick={() => bookRef.current?.pageFlip()?.flipNext()}
              className="p-3 border border-[color:var(--ink)]/20 hover:bg-white transition-colors"
              aria-label={t("albumEditor.nextPage")}
            >
              <ChevronRight size={16} />
            </button>
          </div>

          {album.target_pages && (album.pages || []).length < album.target_pages && (
            <div className="mt-6 flex items-center gap-4 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-4 py-2.5">
              <span>
                {t("albumEditor.pagesShort", { current: (album.pages || []).length, target: album.target_pages, remaining: album.target_pages - (album.pages || []).length })}
              </span>
              <button
                onClick={addBlankPage}
                data-testid={TID.editorAddPage}
                className="inline-flex items-center gap-1.5 whitespace-nowrap bg-[color:var(--coral)] text-[color:var(--paper)] px-3 py-1.5 hover:brightness-110 transition-all"
              >
                <Plus size={13} /> {t("albumEditor.addPage")}
              </button>
            </div>
          )}

          <div className="mt-4">
            {showRepackForm ? (
              <RepackPagesForm
                currentPageCount={(album.pages || []).length}
                currentTargetPages={album.target_pages}
                busy={repacking}
                onCancel={() => setShowRepackForm(false)}
                onSubmit={handleRepackPages}
              />
            ) : (
              <button
                onClick={() => setShowRepackForm(true)}
                data-testid={TID.editorChangePageCount}
                className="text-sm text-[color:var(--muted)] hover:text-[color:var(--ink)] underline underline-offset-2"
              >
                {t("albumEditor.changePageCountLink")}
              </button>
            )}
          </div>

          {album.pages && album.pages.length > 0 && (
            <div className="w-full mt-12 max-w-4xl">
              <div className="eyebrow mb-3 text-center">{t("albumEditor.rearrangePhotos")}</div>
              <PhotoTray
                photoIds={photoSequence()}
                onReorder={reorderPhotoSequence}
              />
            </div>
          )}

          {album.photos && album.photos.length > 0 && (
            <div className="w-full mt-8 max-w-4xl">
              <div className="eyebrow mb-3 text-center">{t("albumEditor.allYourPhotos")}</div>
              <PhotoGallery
                photos={sortedAlbumPhotos}
                placedPhotoIds={new Set((album.pages || []).flatMap((pg) => (pg.items || []).filter((it) => it.type === "photo").map((it) => it.photo_id)))}
                selectedPhotoId={placingPhotoId}
                onSelectPhoto={setPlacingPhotoId}
              />
            </div>
          )}

          {/* Add more photos — same 3 methods as the creation wizard. The AI
              curates just the new ones and appends new pages at the end. */}
          <div className="w-full mt-10 max-w-4xl">
            <div className="eyebrow mb-3 text-center">{t("albumEditor.addMorePhotos")}</div>
            <PhotoUploadMethods
              albumId={id}
              mode="editor"
              photos={[]}
              onPhotosChange={() => loadAlbum()}
              onProcessingStarted={() => {
                notifiedRef.current = false;
                setProcessing(true);
              }}
            />
            <p className="text-xs text-[color:var(--muted)] mt-4 text-center">
              {t("albumEditor.addMorePhotosNote")}
            </p>
          </div>
        </div>

        {/* Barre latérale (Sidebar) */}
        <aside className="lg:sticky lg:top-16 bg-white p-4 border border-[color:var(--border-soft)] max-h-[calc(100vh-5rem)] overflow-y-auto">
          <div className="eyebrow mb-3">{t("albumEditor.tools")}</div>

          <div className="space-y-2 mb-4">
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => albumHistory.undo()}
                disabled={!albumHistory.canUndo()}
                data-testid="editor-undo"
                className="inline-flex items-center justify-center gap-2 border border-[color:var(--ink)]/30 py-2 hover:border-[color:var(--ink)] transition-colors disabled:opacity-40"
                title={t("albumEditor.undoTitle")}
              >
                <Undo2 size={14} />
              </button>
              <button
                onClick={() => albumHistory.redo()}
                disabled={!albumHistory.canRedo()}
                data-testid="editor-redo"
                className="inline-flex items-center justify-center gap-2 border border-[color:var(--ink)]/30 py-2 hover:border-[color:var(--ink)] transition-colors disabled:opacity-40"
                title={t("albumEditor.redoTitle")}
              >
                <Redo2 size={14} />
              </button>
            </div>
            <button
              data-testid={TID.editorSave}
              onClick={save}
              disabled={saving}
              className="w-full inline-flex items-center justify-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] py-2 hover:bg-[color:var(--coral)] transition-colors disabled:opacity-60"
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
              <span className="text-sm font-semibold tracking-widest uppercase">{t("common.save")}</span>
            </button>
            {lastSavedAt && (
              <p className="text-[11px] text-[color:var(--muted)] text-center -mt-1">
                {t("albumEditor.savedAutomatically", { time: lastSavedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) })}
              </p>
            )}
            <button
              data-testid={TID.editorExportPdf}
              onClick={goToOrder}
              disabled={saving}
              className="w-full inline-flex items-center justify-center gap-2 bg-[color:var(--ink)] text-[color:var(--paper)] py-2.5 hover:bg-[color:var(--coral)] transition-colors disabled:opacity-60"
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : <ShoppingBag size={14} />}
              <span className="text-sm font-semibold tracking-widest uppercase">{t("albumEditor.orderThisAlbum")}</span>
            </button>
            <button
              data-testid={TID.editorAddText}
              onClick={() => setPlacingText((v) => !v)}
              className={`w-full inline-flex items-center justify-center gap-2 border py-2 transition-colors ${
                placingText
                  ? "bg-[color:var(--coral)] text-[color:var(--paper)] border-[color:var(--coral)]"
                  : "border-[color:var(--ink)]/30 hover:border-[color:var(--ink)]"
              }`}
            >
              <Type size={14} />
              <span className="text-sm font-semibold tracking-widest uppercase">
                {placingText ? t("albumEditor.clickOnPage") : t("albumEditor.addTextButton")}
              </span>
            </button>
          </div>

          <div className="border-t border-[color:var(--border-soft)] pt-4">
            <div className="eyebrow mb-3">{t("albumEditor.editing")}</div>
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
            ) : selected ? (
              <p className="text-xs text-[color:var(--muted)] leading-relaxed">
                {t("albumEditor.selectedHint")}
              </p>
            ) : (
              <p className="text-xs text-[color:var(--muted)] leading-relaxed">
                {t("albumEditor.nothingSelectedHint")}<br /><br />
                <em>{t("albumEditor.tipLabel")}</em> : {t("albumEditor.tipText")}
              </p>
            )}
          </div>

          <div className="border-t border-[color:var(--border-soft)] pt-6 mt-6">
            <div className="eyebrow mb-3">{t("albumEditor.about")}</div>
            <div className="text-sm text-[color:var(--ink)]/70 space-y-1">
              <div>{t("albumEditor.pagesCount", { count: album.pages?.length || 0 })}</div>
              <div>{t("albumEditor.photosUsed", { count: album.photos?.filter((p) => p.is_selected).length || 0 })}</div>
              <div>{t("albumEditor.formatLine", { size: album.size, orientation: albumOrientation })}</div>
            </div>
          </div>
        </aside>
      </div>
    </main>
  );
}
