import React, { useEffect } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { COVER_DRAWINGS } from "@/lib/coverDrawings";

/** The bank of drawings for the cover: one click puts one on it. */
export default function CoverDrawingPicker({ onPick, onClose }) {
  const { t } = useTranslation();
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return createPortal(
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onClose} data-testid="cover-drawing-picker">
      <div
        className="bg-[color:var(--paper)] max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6 relative"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={t("coverPanel.drawings.title")}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-[color:var(--muted)] hover:text-[color:var(--ink)]" aria-label={t("common.close")}>
          <X size={18} />
        </button>
        <h3 className="font-serif-display text-2xl tracking-tight mb-1 pr-6">{t("coverPanel.drawings.title")}</h3>
        <p className="text-sm text-ink/70 mb-5">{t("coverPanel.drawings.intro")}</p>
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
          {COVER_DRAWINGS.map((d) => (
            <button
              key={d.key}
              type="button"
              onClick={() => {
                onPick(d);
                onClose();
              }}
              className="aspect-square bg-[color:var(--editor-canvas)] border border-transparent hover:border-[color:var(--ink)] transition-colors flex items-center justify-center p-3"
              title={d.name}
              data-testid={`cover-drawing-${d.key}`}
            >
              <img src={d.url} alt={d.name} loading="lazy" decoding="async" className="max-w-full max-h-full object-contain" />
            </button>
          ))}
        </div>
      </div>
    </div>,
    document.body
  );
}
