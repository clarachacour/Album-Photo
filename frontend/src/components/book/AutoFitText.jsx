import React, { useRef, useState, useLayoutEffect, useEffect } from "react";
import { REFERENCE_PAGE_PX } from "@/components/book/textMeasure";

/**
 * Renders a cover text item at a target font size, then checks the
 * ACTUAL rendered element for overflow (scrollWidth/scrollHeight vs
 * clientWidth/clientHeight) and shrinks it if it doesn't fit.
 *
 * This exists because every earlier attempt at this problem — measuring
 * text in a hidden span ahead of time, waiting for document.fonts.ready
 * before measuring, explicitly pre-loading specific fonts — was a
 * *prediction* of what the real render would look like, made before that
 * render happened. Each prediction turned out wrong at least once (a
 * subtitle still clipped in the exported PDF despite every one of those
 * safeguards). Checking the real, already-painted DOM node instead of
 * predicting it can't be wrong the same way, because it isn't a
 * prediction — it's the actual measurement of what's actually on screen,
 * whatever font metrics or loading timing produced it.
 */
/*
 * fitKey: changes when the box or the asked size changes (resized, Size
 *   slider): the text then starts again from the asked size, so it grows
 *   back when there's room again (it used to stay shrunk for good).
 * onFitted(scale): the share of the asked size the text is drawn at, once
 *   it fits (the editor shows the real size on its Size slider).
 * onGrow(factor): asked when a bigger asked size makes the text too tall
 *   for its box: the box can grow (taller by factor) instead of the text
 *   shrinking; returns false when it can't.
 */
export function AutoFitText({ baseFontSize, content, letterSpacing, fitKey, onFitted, onGrow }) {
  const ref = useRef(null);
  const [scale, setScale] = useState(1);
  const attemptsRef = useRef(0);
  const lastFitKeyRef = useRef(fitKey);
  const lastBaseRef = useRef(baseFontSize);
  const growRef = useRef(false);
  const reportedRef = useRef(null);
  const report = (value) => {
    const key = `${baseFontSize}:${value}`;
    if (onFitted && reportedRef.current !== key) {
      reportedRef.current = key;
      onFitted(value);
    }
  };
  // Registers itself as "still possibly correcting" on window while it
  // might need another overflow-correction pass, and un-registers once a
  // render finds no overflow (or gives up at the attempt cap). This is
  // what PrintAlbum.jsx now actually waits on before letting Playwright
  // capture the page — a fixed delay (tried at 500ms, then 1.2s) kept
  // guessing wrong about how long this takes, because it isn't a fixed
  // amount of time: it's however many render-and-remeasure cycles this
  // particular text needs, which varies by word and by how differently
  // sized the print page's physical @page layout is from whatever
  // context it was last measured in.
  const registeredRef = useRef(false);
  const markPending = () => {
    if (registeredRef.current) return;
    registeredRef.current = true;
    if (typeof window !== "undefined") window.__autoFitPending = (window.__autoFitPending || 0) + 1;
  };
  const markSettled = () => {
    if (!registeredRef.current) return;
    registeredRef.current = false;
    if (typeof window !== "undefined") window.__autoFitPending = Math.max(0, (window.__autoFitPending || 0) - 1);
  };

  // Runs after every render on purpose (no dependency list): the text is
  // measured as actually drawn, and a new render may have changed its box.
  // A shrink is followed by one more render to check it; attemptsRef caps
  // that at 6, so it can't go on forever.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useLayoutEffect(() => {
    if (fitKey !== lastFitKeyRef.current) {
      lastFitKeyRef.current = fitKey;
      attemptsRef.current = 0;
      // A bigger asked size: the box may grow to hold it.
      growRef.current = baseFontSize > lastBaseRef.current;
      lastBaseRef.current = baseFontSize;
      if (scale !== 1) {
        markPending();
        setScale(1); // measured again at the asked size, next render
        return;
      }
    }
    const el = ref.current;
    if (!el || !el.clientWidth || !el.clientHeight) {
      markSettled();
      return;
    }
    if (attemptsRef.current > 6) {
      // safety cap — stops any pathological back-and-forth from ever
      // looping forever, and releases the pending flag so a genuinely
      // unfittable case can't block the print export indefinitely
      markSettled();
      return;
    }
    const overflowX = el.scrollWidth / el.clientWidth;
    const overflowY = el.scrollHeight / el.clientHeight;
    const overflow = Math.max(overflowX, overflowY);
    if (growRef.current && onGrow && overflowY > 1.02 && overflowX <= 1.02) {
      growRef.current = false;
      if (onGrow(overflowY * 1.04)) return; // drawn again in its taller box
    }
    if (overflow > 1.02 && scale > 0.3) {
      markPending();
      attemptsRef.current += 1;
      setScale((s) => Math.max(0.3, (s / overflow) * 0.97));
    } else {
      growRef.current = false;
      report(scale);
      markSettled();
    }
  });

  useEffect(() => markSettled, []);

  return (
    <span
      ref={ref}
      className="whitespace-pre-wrap block w-full h-full pointer-events-none select-none"
      style={{
        fontSize: `${(((baseFontSize * scale) / REFERENCE_PAGE_PX) * 100).toFixed(2)}cqw`,
        // Spaced capitals ("O U R  W E D D I N G"), in em of this size. The
        // space also comes after the last letter: the same space on the
        // left keeps a centred line centred.
        ...(letterSpacing ? { letterSpacing: `${letterSpacing}em`, paddingLeft: `${letterSpacing}em` } : {}),
      }}
    >
      {content}
    </span>
  );
}
