import { useState, useLayoutEffect } from "react";
import { measureDomTextWidth } from "@/components/book/textMeasure";

/**
 * Fits the cover title to its box: measures the widest word with a canvas
 * and scales the font size so it fills the full width of the title box —
 * for every template, regardless of word length. This both shrinks long
 * words (e.g. "AUSTRALIA") so they never bleed past the cover edge, and
 * grows short words (e.g. "SICILY") so they aren't left looking small in
 * an oversized box. The stored title_font_size is only used as the
 * starting point for measurement, not as a ceiling.
 */
export function useFitTitleFontSize({ containerWidth, boxWidthFraction, boxHeightFraction, lineCount, text, storedFontSize, fontFamily, fontWeight, uppercase, writingMode, pageAspect, singleLine, scale }) {
  const [fontSize, setFontSize] = useState(storedFontSize || 32);

  useLayoutEffect(() => {
    if (!containerWidth || !text) return;

    if (writingMode) {
      // Vertical title (e.g. "Notre Rencontre"): fit it to the box's real
      // footprint instead of trusting the stored size blindly — the text's
      // rendered *width* becomes its vertical extent once rotated, and the
      // box's own width caps how "thick" it can safely get.
      const compute = () => {
        const REF_PX = 100;
        const lengthPx = boxHeightFraction * containerWidth * pageAspect; // box height -> px (the reading-direction length)
        const thicknessPx = boxWidthFraction * containerWidth; // box width -> px (the cap on stroke thickness)
        const measured = Math.max(
          1,
          measureDomTextWidth(String(text), {
            fontPx: REF_PX,
            fontWeight,
            fontFamily,
            letterSpacing: "-0.025em",
            uppercase,
          })
        );
        const fitted = Math.min(REF_PX * (lengthPx / measured) * 0.92, thicknessPx * 0.92);
        setFontSize(Math.max(8, fitted));
      };
      compute();
      let cancelled = false;
      if (typeof document !== "undefined" && document.fonts && document.fonts.load) {
        const spec = `${fontWeight || 400} 16px ${fontFamily}`;
        Promise.all([document.fonts.load(spec), document.fonts.ready])
          .then(() => {
            if (!cancelled) compute();
          })
          .catch(() => {});
      }
      return () => {
        cancelled = true;
      };
    }

    const compute = () => {
      const boxWidthPx = boxWidthFraction * containerWidth;
      const REF_PX = 100; // fixed reference size for measurement; only the ratio matters

      // Single-line titles ("Our Forever Journey" on one row) measure the
      // whole string at once; multi-line titles (one word per line) fit to
      // whichever individual word is widest.
      const words = singleLine ? [String(text)] : String(text).split(" ");
      const widestAtRef = Math.max(
        1,
        ...words.map((w) =>
          measureDomTextWidth(w, {
            fontPx: REF_PX,
            fontWeight,
            fontFamily,
            letterSpacing: "-0.025em", // matches the title's `tracking-tight` class
            uppercase,
          })
        )
      );

      // SAFETY is the "fill 100% of the box" baseline; `scale` (1 = fill
      // exactly, <1 shrinks, >1 grows past the box edge if pushed hard) is
      // the only thing the size slider in the right panel controls now.
      // Without a scale term here, any value the slider writes to
      // storedFontSize cancels out of this ratio algebraically — that's
      // the bug that made the slider look like it stopped doing anything.
      const SAFETY = 0.96 * (scale ?? 1);
      let fitted = REF_PX * (boxWidthPx / widestAtRef) * SAFETY;

      // Cap by the box's own height so a short word in a MULTI-line title
      // (e.g. "Our" / "Forever" / "Journey") can't grow past what the box can
      // actually hold once every line is stacked. A single-word title has no
      // such risk — capping it too would silently override the width-fill
      // goal using the stored title_h, which was sized for the old, smaller
      // static font and is often too short for a true full-width fit.
      if (boxHeightFraction && lineCount > 1) {
        const boxHeightPx = boxHeightFraction * containerWidth * pageAspect; // height = width * (page height / page width)
        const maxByHeight = (boxHeightPx / lineCount) * 0.92;
        fitted = Math.min(fitted, maxByHeight);
      }

      setFontSize(Math.max(10, fitted));
    };

    // Measure immediately for a fast first paint...
    compute();

    // ...then re-measure once the real @font-face is confirmed loaded. Since
    // this now measures a real DOM element with the same font-family, this
    // re-run is what corrects an initial fallback-font measurement — no
    // manual per-property math needed for whichever font is actually active.
    let cancelled = false;
    if (typeof document !== "undefined" && document.fonts && document.fonts.load) {
      const spec = `${fontWeight || 400} 16px ${fontFamily}`;
      Promise.all([document.fonts.load(spec), document.fonts.ready])
        .then(() => {
          if (!cancelled) compute();
        })
        .catch(() => {});
    }
    return () => {
      cancelled = true;
    };
  }, [containerWidth, boxWidthFraction, boxHeightFraction, lineCount, text, storedFontSize, fontFamily, fontWeight, uppercase, writingMode, pageAspect, singleLine, scale]);

  return fontSize;
}
