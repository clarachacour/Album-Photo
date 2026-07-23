import React, { useRef, useEffect } from "react";
import HTMLFlipBook from "react-pageflip";

/**
 * Flipbook wrapper. children = array of page nodes.
 * The book always shows 2 pages side-by-side.
 */
export default function Flipbook({ children, orientation = "portrait", onFlip, bookRef }) {
  const localRef = useRef();
  const ref = bookRef || localRef;

  // Compute dimensions relative to viewport
  const isLandscape = orientation === "landscape";
  const pageW = isLandscape ? 520 : 380;
  const pageH = isLandscape ? 380 : 540;

  return (
    <div className="flipbook-wrapper select-none">
      <HTMLFlipBook
        ref={ref}
        width={pageW}
        height={pageH}
        size="stretch"
        minWidth={280}
        maxWidth={720}
        minHeight={360}
        maxHeight={900}
        maxShadowOpacity={0.4}
        showCover={true}
        mobileScrollSupport={true}
        drawShadow={true}
        flippingTime={700}
        usePortrait={false}
        startPage={0}
        onFlip={(e) => onFlip && onFlip(e.data)}
        className="album-flipbook"
      >
        {children}
      </HTMLFlipBook>
    </div>
  );
}
