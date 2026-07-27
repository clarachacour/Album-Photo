import React, { useState, useRef, useEffect, useImperativeHandle } from "react";

/**
 * Custom, React-19-safe 3D flipbook that mirrors a real physical book:
 * - The front cover is shown ALONE first (like a closed book on a table)
 * - Turning the page reveals real double-page spreads, with a visible spine
 *   (the shadowed gutter) between the two pages
 * - The very last page (back cover) is shown alone too, same as a physical book
 *
 * The outer frame is always sized as a full two-page spread — solo pages
 * (cover/back cover) are centered *within* that same fixed-size frame instead
 * of shrinking the whole container, so there's no jarring resize/flash when
 * moving between a solo page and a spread.
 *
 * `pages` is the flat sequence [cover, blank, ...interior, blank, backCover].
 * Internally this is split into "views": the first and last item are solo,
 * everything in between is paired up into spreads.
 */
const CustomFlipbook = React.forwardRef(function CustomFlipbook({ pages, orientation = "portrait", onFlip }, ref) {
  const views = buildViews(pages);
  const [viewIdx, setViewIdx] = useState(0);
  const [flipping, setFlipping] = useState(null); // "next" | "prev" | null
  const totalViews = views.length;
  const prevTotalRef = useRef(totalViews);
  const wasAtEndRef = useRef(false);

  // If the reader was on the last view (the back cover) and more content
  // gets appended (e.g. "Add more photos"), follow along to the new last
  // view instead of leaving them stranded on a page that's now in the middle.
  useEffect(() => {
    if (totalViews !== prevTotalRef.current) {
      if (wasAtEndRef.current) {
        setViewIdx(totalViews - 1);
      } else {
        setViewIdx((v) => Math.min(v, totalViews - 1));
      }
      prevTotalRef.current = totalViews;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [totalViews]);

  useEffect(() => {
    wasAtEndRef.current = viewIdx === totalViews - 1;
  }, [viewIdx, totalViews]);

  const current = views[Math.min(viewIdx, totalViews - 1)];
  const next = views[viewIdx + 1];
  const prev = views[viewIdx - 1];

  const canNext = viewIdx < totalViews - 1;
  const canPrev = viewIdx > 0;

  const flipNext = () => {
    if (flipping || !canNext) return;
    setFlipping("next");
    setTimeout(() => {
      setViewIdx((v) => Math.min(v + 1, totalViews - 1));
      setFlipping(null);
      onFlip && onFlip(viewIdx + 1);
    }, 700);
  };

  const flipPrev = () => {
    if (flipping || !canPrev) return;
    setFlipping("prev");
    setTimeout(() => {
      setViewIdx((v) => Math.max(v - 1, 0));
      setFlipping(null);
      onFlip && onFlip(viewIdx - 1);
    }, 700);
  };

  useImperativeHandle(ref, () => ({
    pageFlip: () => ({ flipNext, flipPrev }),
    flipNext,
    flipPrev,
    goToEnd: () => setViewIdx(totalViews - 1),
    goToStart: () => setViewIdx(0),
    getSpread: () => viewIdx,
  }));

  const soloMode = current.type === "solo";

  return (
    <div className="w-full flex justify-center">
      <div className="relative" style={{ perspective: "2200px", transformStyle: "preserve-3d" }}>
        {/* Frame is ALWAYS the same size as a full spread — a solo cover is
            centered inside it at its own natural (half-width) proportions,
            so there's never a resize between views (which was causing the
            page-flip animation to visibly stretch/distort mid-turn). */}
        <div className="relative" style={sizeStyle(orientation)}>
          {soloMode ? (
            <div className="absolute inset-0 flex justify-center">
              <div className="relative h-full book-shadow bg-[color:var(--paper)] overflow-visible" style={{ width: "50%" }}>
                {current.pages[0]}
              </div>
            </div>
          ) : (
            <div className="absolute inset-0 grid grid-cols-2 gap-0 book-shadow bg-[color:var(--paper)]">
              <div className="relative overflow-visible page-inner-shadow">{current.pages[0]}</div>
              <div className="relative overflow-visible page-inner-shadow-right">{current.pages[1]}</div>
              {/* The spine — the visible binding/gutter between the two pages */}
              <div
                className="absolute top-0 bottom-0 left-1/2 -translate-x-1/2 pointer-events-none z-10"
                style={{
                  width: "14px",
                  background: "linear-gradient(90deg, rgba(0,0,0,0.16), rgba(0,0,0,0.03) 35%, rgba(0,0,0,0.03) 65%, rgba(0,0,0,0.16))",
                }}
              />
            </div>
          )}

          {/* NEXT flip overlay — always animates the right-hand slot, whether
              that's a spread's right page or a right-aligned solo cover. */}
          {flipping === "next" && (
            <div
              className="absolute top-0 h-full"
              style={{
                left: "50%",
                width: "50%",
                transformStyle: "preserve-3d",
                transformOrigin: "left center",
                animation: "flipNextAnim 700ms ease-in-out forwards",
                zIndex: 20,
              }}
            >
              <div
                className="absolute inset-0 overflow-visible page-inner-shadow-right bg-[color:var(--paper)]"
                style={{ backfaceVisibility: "hidden" }}
              >
                {soloMode ? (viewIdx === 0 ? current.pages[0] : blankPage(orientation)) : current.pages[1]}
              </div>
              <div
                className="absolute inset-0 overflow-visible page-inner-shadow bg-[color:var(--paper)]"
                style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}
              >
                {next ? next.pages[0] : blankPage(orientation)}
              </div>
            </div>
          )}

          {/* PREV flip overlay — always animates the left-hand slot. */}
          {flipping === "prev" && (
            <div
              className="absolute top-0 h-full"
              style={{
                left: "0%",
                width: "50%",
                transformStyle: "preserve-3d",
                transformOrigin: "right center",
                animation: "flipPrevAnim 700ms ease-in-out forwards",
                zIndex: 20,
              }}
            >
              <div
                className="absolute inset-0 overflow-visible page-inner-shadow bg-[color:var(--paper)]"
                style={{ backfaceVisibility: "hidden" }}
              >
                {soloMode ? (viewIdx !== 0 ? current.pages[0] : blankPage(orientation)) : current.pages[0]}
              </div>
              <div
                className="absolute inset-0 overflow-visible page-inner-shadow-right bg-[color:var(--paper)]"
                style={{ backfaceVisibility: "hidden", transform: "rotateY(-180deg)" }}
              >
                {prev ? prev.pages[prev.pages.length - 1] : blankPage(orientation)}
              </div>
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes flipNextAnim {
          from { transform: rotateY(0deg); }
          to { transform: rotateY(-180deg); }
        }
        @keyframes flipPrevAnim {
          from { transform: rotateY(0deg); }
          to { transform: rotateY(180deg); }
        }
      `}</style>
    </div>
  );
});

/**
 * Splits the flat page sequence into a list of views: the first page
 * (front cover) and last page (back cover) are always solo; everything
 * between is paired into spreads of two.
 */
function buildViews(pages) {
  if (pages.length === 0) return [{ type: "solo", pages: [null] }];
  if (pages.length === 1) return [{ type: "solo", pages: [pages[0]] }];

  const views = [{ type: "solo", pages: [pages[0]] }];
  const middle = pages.slice(1, pages.length - 1);
  for (let i = 0; i < middle.length; i += 2) {
    if (i + 1 < middle.length) {
      views.push({ type: "spread", pages: [middle[i], middle[i + 1]] });
    } else {
      views.push({ type: "solo", pages: [middle[i]] });
    }
  }
  views.push({ type: "solo", pages: [pages[pages.length - 1]] });
  return views;
}

function sizeStyle(orientation) {
  if (orientation === "landscape") {
    return { width: "min(1180px, 92vw, 195vh)", aspectRatio: "2.828 / 1" };
  }
  return { width: "min(860px, 88vw, 98vh)", aspectRatio: "2 / 1.414" };
}

function blankPage(orientation) {
  const aspect = orientation === "landscape" ? "aspect-[1.414/1]" : "aspect-[1/1.414]";
  return <div className={`w-full ${aspect} bg-[color:var(--paper)]`} />;
}

export default CustomFlipbook;