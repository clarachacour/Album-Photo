import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";

// Remembers, per browser, which guides the person has finished or skipped.
const seenKey = (id) => `everbook_tour_${id}_seen`;
function hasSeen(id) {
  try {
    return localStorage.getItem(seenKey(id)) === "1";
  } catch {
    return true; // no storage: don't pop up on every visit
  }
}
function markSeen(id) {
  try {
    localStorage.setItem(seenKey(id), "1");
  } catch {
    /* storage unavailable */
  }
}

// The first *visible* element matching the selector (a flipbook keeps
// hidden copies of some pages in the DOM).
function findTarget(selector) {
  if (!selector) return null;
  for (const el of document.querySelectorAll(selector)) {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) return el;
  }
  return null;
}

/**
 * A step-by-step guide over the page: each step highlights one element
 * (`target`, a CSS selector — or none for a centered message) and explains
 * it in a bubble; an optional `prepare(context)` gets the page ready first
 * (`context` is whatever the page passes, e.g. functions to turn to a page).
 * Texts come from the locale files: <prefix>.<key>.title and <prefix>.<key>.body.
 *
 *   const tour = useGuidedTour({ id: "editor", prefix: "tour.editor", steps, autoStart: ready });
 *   <button onClick={tour.start}>Guide</button>
 *   {tour.element}
 *
 * Opens by itself the first time (autoStart) and never again once finished
 * or skipped; tour.start() replays it.
 */
export function useGuidedTour({ id, prefix, steps, autoStart = false, context }) {
  const [index, setIndex] = useState(null); // null = closed
  const contextRef = useRef(context);
  contextRef.current = context;
  const start = useCallback(() => setIndex(0), []);
  const close = useCallback(() => {
    markSeen(id);
    setIndex(null);
  }, [id]);

  useEffect(() => {
    if (!autoStart || hasSeen(id)) return;
    // Let the page finish laying out before measuring anything.
    const timer = setTimeout(() => setIndex((i) => (i === null ? 0 : i)), 700);
    return () => clearTimeout(timer);
  }, [autoStart, id]);

  const element =
    index === null
      ? null
      : createPortal(
          <TourStep
            step={steps[index]}
            contextRef={contextRef}
            prefix={prefix}
            index={index}
            count={steps.length}
            onPrev={() => setIndex((i) => Math.max(0, i - 1))}
            onNext={() => (index + 1 < steps.length ? setIndex(index + 1) : close())}
            onClose={close}
          />,
          document.body
        );
  return { start, element, open: index !== null };
}

const PAD = 8; // space around the highlighted element
const BUBBLE_W = 340;

function TourStep({ step, contextRef, prefix, index, count, onPrev, onNext, onClose }) {
  const { t } = useTranslation();
  const [rect, setRect] = useState(null);
  const bubbleRef = useRef(null);
  const [bubbleH, setBubbleH] = useState(200);
  const isLast = index + 1 === count;

  // Get the page ready for the step (e.g. turn to a page), bring the
  // element into view, then follow it (scroll, resize, layout).
  useEffect(() => {
    let frame;
    step.prepare?.(contextRef.current);
    const scrollTimer = setTimeout(() => {
      findTarget(step.target)?.scrollIntoView({ block: "center", behavior: "smooth" });
    }, step.prepare ? 150 : 0);
    const follow = () => {
      const target = findTarget(step.target);
      const r = target?.getBoundingClientRect();
      setRect((prev) => {
        if (!r) return null;
        const next = { top: r.top, left: r.left, width: r.width, height: r.height };
        return prev && Object.keys(next).every((k) => Math.abs(prev[k] - next[k]) < 0.5) ? prev : next;
      });
      frame = requestAnimationFrame(follow);
    };
    follow();
    return () => {
      clearTimeout(scrollTimer);
      cancelAnimationFrame(frame);
    };
  }, [step, contextRef]);

  // The bubble's height decides whether it fits below the highlight.
  useLayoutEffect(() => {
    const el = bubbleRef.current;
    if (!el) return;
    setBubbleH(el.offsetHeight);
    const ro = new ResizeObserver(() => setBubbleH(el.offsetHeight));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight") onNext();
      else if (e.key === "ArrowLeft") onPrev();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, onNext, onPrev]);

  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const narrow = vw < 640;
  // Bubble next to the highlight: below if it fits, else above, else on
  // the side; kept inside the screen. On phones, docked at the bottom.
  let bubbleStyle;
  if (narrow) {
    bubbleStyle = { left: 12, right: 12, bottom: 12 };
  } else if (!rect) {
    bubbleStyle = { left: vw / 2 - BUBBLE_W / 2, top: vh / 2 - bubbleH / 2, width: BUBBLE_W };
  } else {
    const left = Math.min(Math.max(16, rect.left + rect.width / 2 - BUBBLE_W / 2), vw - BUBBLE_W - 16);
    const below = rect.top + rect.height + PAD + 12;
    const above = rect.top - PAD - 12 - bubbleH;
    const sideTop = Math.min(Math.max(16, rect.top + rect.height / 2 - bubbleH / 2), vh - bubbleH - 16);
    const right = rect.left + rect.width + PAD + 12;
    const leftSide = rect.left - PAD - 12 - BUBBLE_W;
    if (below + bubbleH < vh - 16) bubbleStyle = { left, top: below, width: BUBBLE_W };
    else if (above > 16) bubbleStyle = { left, top: above, width: BUBBLE_W };
    // No room above or below: beside it, so it doesn't hide what it explains.
    else if (right + BUBBLE_W < vw - 16) bubbleStyle = { left: right, top: sideTop, width: BUBBLE_W };
    else if (leftSide > 16) bubbleStyle = { left: leftSide, top: sideTop, width: BUBBLE_W };
    else bubbleStyle = { left, top: Math.max(16, vh - bubbleH - 16), width: BUBBLE_W };
  }

  const key = `${prefix}.${step.key}`;
  return (
    <div className="fixed inset-0 z-[200]" role="dialog" aria-modal="true" aria-labelledby="tour-title" data-testid="guided-tour">
      {/* Dims everything except the highlighted element; clicks on the page are paused during the guide. */}
      {rect ? (
        <div
          className="absolute rounded-sm transition-all duration-200 pointer-events-none"
          style={{
            top: rect.top - PAD,
            left: rect.left - PAD,
            width: rect.width + PAD * 2,
            height: rect.height + PAD * 2,
            boxShadow: "0 0 0 9999px rgba(26, 26, 23, 0.55)",
            outline: "2px solid var(--coral)",
          }}
        />
      ) : (
        <div className="absolute inset-0 bg-[rgba(26,26,23,0.55)]" />
      )}
      <div
        ref={bubbleRef}
        className="absolute bg-white shadow-2xl border border-[color:var(--border-soft)] p-5"
        style={bubbleStyle}
        aria-live="polite"
      >
        <div className="flex items-start justify-between gap-4 mb-2">
          <h2 id="tour-title" className="font-serif-display text-xl leading-tight">{t(`${key}.title`)}</h2>
          <button onClick={onClose} aria-label={t("tour.skip")} className="text-[color:var(--muted)] hover:text-[color:var(--ink)] shrink-0" data-testid="tour-close">
            <X size={16} />
          </button>
        </div>
        <p className="text-sm text-[color:var(--ink)]/80 leading-relaxed mb-5">{t(`${key}.body`)}</p>
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs text-[color:var(--muted)]" data-testid="tour-progress">
            {index + 1} / {count}
          </span>
          <div className="flex items-center gap-2">
            {index > 0 ? (
              <button onClick={onPrev} className="px-3 py-2 text-xs font-semibold tracking-widest uppercase text-[color:var(--muted)] hover:text-[color:var(--ink)]">
                {t("tour.prev")}
              </button>
            ) : (
              <button onClick={onClose} className="px-3 py-2 text-xs font-semibold tracking-widest uppercase text-[color:var(--muted)] hover:text-[color:var(--ink)]" data-testid="tour-skip">
                {t("tour.skip")}
              </button>
            )}
            <button
              onClick={onNext}
              autoFocus
              className="px-4 py-2 bg-[color:var(--ink)] text-[color:var(--paper)] text-xs font-semibold tracking-widest uppercase hover:bg-[color:var(--coral)] transition-colors"
              data-testid="tour-next"
            >
              {isLast ? t("tour.done") : t("tour.next")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** The small "Guide" button that replays a tour. */
export function TourHelpButton({ onClick, className = "" }) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      onClick={onClick}
      data-tour="tour-help"
      data-testid="tour-help"
      className={`inline-flex items-center gap-1.5 border border-[color:var(--ink)]/20 px-3 py-1.5 text-xs font-semibold tracking-widest uppercase text-[color:var(--ink)]/70 hover:border-[color:var(--ink)] hover:text-[color:var(--ink)] transition-colors ${className}`}
    >
      <span aria-hidden="true" className="inline-flex items-center justify-center w-4 h-4 rounded-full border border-current text-[10px] leading-none">?</span>
      {t("tour.help")}
    </button>
  );
}
