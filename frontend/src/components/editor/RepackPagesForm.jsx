import React, { useState } from "react";
import { useTranslation, Trans } from "react-i18next";
import { Loader2 } from "lucide-react";
import { spreadNumberToPageCount } from "@/components/editor/spreads";

// Lets the person shrink or grow an already-created album's total page
// count without starting over — e.g. "this 150-page album is too much,
// make it 100" — while keeping however many pages up front (title page,
// plus anything already hand-edited) untouched. Every page holds at most 4
// photos, so the backend refuses outright (rather than silently dropping
// photos) if the requested page count is too small to physically fit
// everything currently on the pages being touched.

export function RepackPagesForm({ currentPageCount, currentTargetPages, busy, onCancel, onSubmit }) {
  const { t } = useTranslation();
  const [targetPages, setTargetPages] = useState(currentTargetPages || currentPageCount);
  // Defaults to protecting the *entire* current album, not just the first
  // spread — with the old default of 1, simply raising the page count
  // (the single most common reason to open this form) silently rebuilt
  // every spread after the very first one, discarding any reordering or
  // layout changes already made. Redistributing content only makes sense
  // when *lowering* the page count (there's less room, something has to
  // move); adding pages never requires touching anything that already
  // exists — new blank pages can simply be appended. The person can still
  // lower this manually for the cases that do call for a reflow.
  const currentLastSpread = Math.max(1, Math.ceil((currentPageCount + 3) / 2));
  const [keepUpToSpread, setKeepUpToSpread] = useState(currentLastSpread);
  const keepFirstPages = Math.min(currentPageCount, spreadNumberToPageCount(keepUpToSpread));

  return (
    <div className="border border-[color:var(--border-soft)] bg-[color:var(--editor-canvas)] p-4 max-w-md">
      <div className="text-sm font-semibold mb-3">{t("albumEditor.repack.title")}</div>
      {/* Label at the top, input at the bottom of each column: the two inputs
          stay aligned even when one label wraps onto two lines. */}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div className="flex flex-col justify-between">
          <label className="text-xs text-[color:var(--muted)] block mb-1">{t("albumEditor.repack.newTotal")}</label>
          <input
            type="number"
            min={1}
            value={targetPages}
            onChange={(e) => setTargetPages(Math.max(1, parseInt(e.target.value, 10) || 1))}
            className="w-full px-2 py-1.5 border border-[color:var(--ink)]/30 text-sm"
          />
        </div>
        <div className="flex flex-col justify-between">
          <label className="text-xs text-[color:var(--muted)] block mb-1">{t("albumEditor.repack.rebuildAfter")}</label>
          <input
            type="number"
            min={1}
            value={keepUpToSpread}
            onChange={(e) => setKeepUpToSpread(Math.max(1, parseInt(e.target.value, 10) || 1))}
            className="w-full px-2 py-1.5 border border-[color:var(--ink)]/30 text-sm"
          />
        </div>
      </div>
      <p className="text-xs text-[color:var(--muted)] mb-4">
        <Trans
          i18nKey="albumEditor.repack.explanation"
          components={{ 1: <span className="font-medium text-[color:var(--ink)]/80" /> }}
        />
      </p>
      <div className="flex gap-2">
        <button
          onClick={onCancel}
          disabled={busy}
          className="text-sm px-3 py-1.5 text-[color:var(--muted)] hover:text-[color:var(--ink)]"
        >
          {t("common.cancel")}
        </button>
        <button
          onClick={() => onSubmit({ targetPages, keepFirstPages })}
          disabled={busy}
          className="inline-flex items-center gap-1.5 text-sm bg-[color:var(--coral)] text-[color:var(--paper)] px-3 py-1.5 hover:brightness-110 transition-all disabled:opacity-60"
        >
          {busy && <Loader2 size={13} className="animate-spin" />}
          {busy ? t("albumEditor.repack.rebuilding") : t("albumEditor.repack.apply")}
        </button>
      </div>
    </div>
  );
}
