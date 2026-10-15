import React, { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, Check } from "lucide-react";
import { FONTS, fontName } from "@/lib/fonts";
import { useWithoutHistory } from "@/lib/historyPreview";

const LIST_MAX_HEIGHT = 288;

/**
 * A font list where each font is written in itself. Hovering (or moving
 * to) a font shows it on the text being edited straight away; a click
 * chooses it. Leaving the list, Escape or a click elsewhere puts the font
 * back as it was. The tries aren't saved in the undo history: only the
 * font chosen is one step.
 */
export function FontPicker({ value, onChange, tid, dark = false, preferUp = false, className = "" }) {
  const { t } = useTranslation();
  const withoutHistory = useWithoutHistory();
  const [open, setOpen] = useState(false);
  // Above the button when asked and there's room: on a page, the list
  // opening downwards would hide the very text it changes.
  const [up, setUp] = useState(false);
  const [maxHeight, setMaxHeight] = useState(LIST_MAX_HEIGHT);
  const rootRef = useRef(null);
  // The font as it was when the list opened: what a try goes back to.
  const committedRef = useRef(value);
  const shownRef = useRef(value);

  const show = (font) => {
    if (font === shownRef.current) return;
    shownRef.current = font;
    withoutHistory(() => onChange(font));
  };

  const openList = () => {
    committedRef.current = value;
    shownRef.current = value;
    // Room above, below the site's menu bar (64px): a shorter list that
    // scrolls is better than one hiding the text.
    const roomAbove = (rootRef.current?.getBoundingClientRect().top ?? 0) - 72;
    const goUp = preferUp && roomAbove >= 160;
    setUp(goUp);
    setMaxHeight(goUp ? Math.min(LIST_MAX_HEIGHT, roomAbove) : LIST_MAX_HEIGHT);
    setOpen(true);
  };

  const close = () => {
    show(committedRef.current);
    setOpen(false);
  };

  const choose = (font) => {
    // Back to the font from before the tries, then the choice as one
    // undoable step.
    show(committedRef.current);
    if (font !== committedRef.current) onChange(font);
    shownRef.current = font;
    committedRef.current = font;
    setOpen(false);
  };

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (e) => {
      if (!rootRef.current?.contains(e.target)) close();
    };
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
      }
    };
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKey, true);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const current = open ? committedRef.current : value;
  return (
    <div ref={rootRef} className={`relative min-w-0 ${className}`}>
      <button
        type="button"
        data-testid={tid}
        aria-label={t("coverPanel.font")}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => (open ? close() : openList())}
        className={
          dark
            ? "w-full inline-flex items-center justify-between gap-1 bg-transparent text-[color:var(--paper)] text-xs border border-white/30 rounded-sm px-1.5 py-1"
            : "w-full inline-flex items-center justify-between gap-1 border border-[color:var(--ink)]/20 px-2 py-1.5 text-sm bg-white focus:border-[color:var(--ink)] focus:outline-none"
        }
      >
        <span className="truncate" style={{ fontFamily: current }}>{fontName(current)}</span>
        <ChevronDown size={12} className="shrink-0 opacity-60" />
      </button>
      {open && (
        <ul
          role="listbox"
          aria-label={t("coverPanel.font")}
          onMouseLeave={() => show(committedRef.current)}
          style={{ maxHeight }}
          className={`absolute left-0 ${up ? "bottom-full mb-1" : "top-full mt-1"} z-50 min-w-full w-max max-w-[260px] overflow-y-auto bg-white text-[color:var(--ink)] border border-[color:var(--ink)]/20 shadow-lg py-1`}
          data-testid={tid ? `${tid}-list` : undefined}
        >
          {FONTS.map((f) => (
            <li key={f.value} role="option" aria-selected={f.value === committedRef.current}>
              <button
                type="button"
                data-font={f.name}
                onMouseEnter={() => show(f.value)}
                onFocus={() => show(f.value)}
                onClick={() => choose(f.value)}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-[color:var(--editor-canvas)] focus:bg-[color:var(--editor-canvas)] focus:outline-none"
              >
                <span className="w-3 shrink-0">{f.value === committedRef.current && <Check size={12} />}</span>
                <span className="text-base leading-tight" style={{ fontFamily: f.value }}>{f.name}</span>
                {f.kind && <span className="ml-auto pl-2 text-[10px] text-[color:var(--muted)] font-sans">{t(`coverPanel.fonts.${f.kind}`)}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
