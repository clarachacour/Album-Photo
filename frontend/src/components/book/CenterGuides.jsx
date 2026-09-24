import React from "react";

/**
 * Alignment guide lines shown while dragging an item — appear when it lines
 * up with the page center OR with another element on the page (matching
 * edge/edge, center/center, edge/center...), at whatever position that is.
 */
export function CenterGuides({ show, guideX, guideY }) {
  if (!show) return null;
  return (
    <>
      {guideX != null && (
        <div className="absolute top-0 bottom-0 w-px bg-[color:var(--coral)] pointer-events-none z-30" style={{ left: `${guideX * 100}%` }} />
      )}
      {guideY != null && (
        <div className="absolute left-0 right-0 h-px bg-[color:var(--coral)] pointer-events-none z-30" style={{ top: `${guideY * 100}%` }} />
      )}
    </>
  );
}
