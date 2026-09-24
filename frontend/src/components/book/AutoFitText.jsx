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
export function AutoFitText({ baseFontSize, content }) {
  const ref = useRef(null);
  const [scale, setScale] = useState(1);
  const attemptsRef = useRef(0);
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

  useLayoutEffect(() => {
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
    if (overflow > 1.02 && scale > 0.3) {
      markPending();
      attemptsRef.current += 1;
      setScale((s) => Math.max(0.3, (s / overflow) * 0.97));
    } else {
      markSettled();
    }
  });

  useEffect(() => markSettled, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <span
      ref={ref}
      className="whitespace-pre-wrap block w-full h-full pointer-events-none select-none"
      style={{ fontSize: `${(((baseFontSize * scale) / REFERENCE_PAGE_PX) * 100).toFixed(2)}cqw` }}
    >
      {content}
    </span>
  );
}
