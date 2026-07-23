import React, { useState, useRef, useEffect, useImperativeHandle } from "react";

/**
 * Custom, React-19-safe 3D flipbook.
 * - Renders two pages side by side (spread)
 * - Animates a page turn with CSS 3D rotateY when navigating forward or backward
 * - Exposes flipNext() / flipPrev() via ref (compatible with existing editor code)
 */
const CustomFlipbook = React.forwardRef(function CustomFlipbook({ pages, orientation = "portrait", onFlip }, ref) {
  // `spread` is 0-indexed pair number. Spread 0 shows pages[0] + pages[1].
  const [spread, setSpread] = useState(0);
  const [flipping, setFlipping] = useState(null); // "next" | "prev" | null
  const total = pages.length;
  const totalSpreads = Math.max(1, Math.ceil(total / 2));

  const leftIdx = spread * 2;
  const rightIdx = spread * 2 + 1;

  // Precompute source pages for the animation overlays
  const leftPage = pages[leftIdx] ?? blankPage(orientation);
  const rightPage = pages[rightIdx] ?? blankPage(orientation);
  const nextRightPage = pages[rightIdx + 2] ?? blankPage(orientation);
  const nextLeftPage = pages[leftIdx + 2] ?? blankPage(orientation);
  const prevLeftPage = pages[leftIdx - 2] ?? blankPage(orientation);
  const prevRightPage = pages[leftIdx - 1] ?? blankPage(orientation);

  const canNext = spread < totalSpreads - 1;
  const canPrev = spread > 0;

  const flipNext = () => {
    if (flipping || !canNext) return;
    setFlipping("next");
    setTimeout(() => {
      setSpread((s) => Math.min(s + 1, totalSpreads - 1));
      setFlipping(null);
      onFlip && onFlip(spread + 1);
    }, 700);
  };

  const flipPrev = () => {
    if (flipping || !canPrev) return;
    setFlipping("prev");
    setTimeout(() => {
      setSpread((s) => Math.max(s - 1, 0));
      setFlipping(null);
      onFlip && onFlip(spread - 1);
    }, 700);
  };

  useImperativeHandle(ref, () => ({
    pageFlip: () => ({ flipNext, flipPrev }),
    flipNext,
    flipPrev,
    getSpread: () => spread,
  }));

  return (
    <div className="w-full flex justify-center">
      <div
        className="relative"
        style={{
          perspective: "2200px",
          transformStyle: "preserve-3d",
        }}
      >
        <div className="grid grid-cols-2 gap-0 book-shadow bg-[color:var(--paper)]" style={sizeStyle(orientation)}>
          {/* Static left */}
          <div className="relative overflow-hidden page-inner-shadow">
            {leftPage}
          </div>
          {/* Static right */}
          <div className="relative overflow-hidden page-inner-shadow-right">
            {rightPage}
          </div>

          {/* NEXT flip overlay: right side rotates from 0 to -180 */}
          {flipping === "next" && (
            <div
              className="absolute top-0 right-0 h-full"
              style={{
                width: "50%",
                transformStyle: "preserve-3d",
                transformOrigin: "left center",
                animation: "flipNextAnim 700ms ease-in-out forwards",
                zIndex: 20,
              }}
            >
              <div
                className="absolute inset-0 overflow-hidden page-inner-shadow-right"
                style={{ backfaceVisibility: "hidden", background: "var(--paper)" }}
              >
                {rightPage}
              </div>
              <div
                className="absolute inset-0 overflow-hidden page-inner-shadow"
                style={{
                  backfaceVisibility: "hidden",
                  transform: "rotateY(180deg)",
                  background: "var(--paper)",
                }}
              >
                {nextLeftPage}
              </div>
            </div>
          )}

          {/* PREV flip overlay: left side rotates from 0 to +180 */}
          {flipping === "prev" && (
            <div
              className="absolute top-0 left-0 h-full"
              style={{
                width: "50%",
                transformStyle: "preserve-3d",
                transformOrigin: "right center",
                animation: "flipPrevAnim 700ms ease-in-out forwards",
                zIndex: 20,
              }}
            >
              <div
                className="absolute inset-0 overflow-hidden page-inner-shadow"
                style={{ backfaceVisibility: "hidden", background: "var(--paper)" }}
              >
                {leftPage}
              </div>
              <div
                className="absolute inset-0 overflow-hidden page-inner-shadow-right"
                style={{
                  backfaceVisibility: "hidden",
                  transform: "rotateY(-180deg)",
                  background: "var(--paper)",
                }}
              >
                {prevRightPage}
              </div>
            </div>
          )}
        </div>

        {/* Peek layers behind for depth (reveals during animation) */}
        {flipping === "next" && (
          <div className="absolute top-0 right-0 h-full grid grid-cols-1 pointer-events-none" style={{ width: "50%", zIndex: 5 }}>
            <div className="relative overflow-hidden page-inner-shadow-right">{nextRightPage}</div>
          </div>
        )}
        {flipping === "prev" && (
          <div className="absolute top-0 left-0 h-full grid grid-cols-1 pointer-events-none" style={{ width: "50%", zIndex: 5 }}>
            <div className="relative overflow-hidden page-inner-shadow">{prevLeftPage}</div>
          </div>
        )}
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

function sizeStyle(orientation) {
  if (orientation === "landscape") {
    // book opens to double landscape → spread is 2x1.414 landscape pages side by side (wide)
    // Each page: 1.414:1 aspect → total spread 2.828:1
    return { width: "min(1040px, 90vw)", aspectRatio: "2.828 / 1" };
  }
  // portrait pages: each 1 : 1.414 → total spread 2 : 1.414
  return { width: "min(760px, 90vw)", aspectRatio: "2 / 1.414" };
}

function blankPage(orientation) {
  const aspect = orientation === "landscape" ? "aspect-[1.414/1]" : "aspect-[1/1.414]";
  return <div className={`w-full ${aspect} bg-[color:var(--paper)]`} />;
}

export default CustomFlipbook;
