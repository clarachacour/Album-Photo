import React from "react";

const LINE_MM = 0.1; // about 0.25 pt, the usual hairline for marks

/**
 * Crop marks for the printer, drawn on a sheet (mm): at each corner of the
 * trimmed area, two short lines in the margin outside the bleed, lined up
 * with the cut. `folds` (mm from the sheet's top-left) adds the same short
 * lines where the cover folds (boards, hinges, spine), top and bottom /
 * left and right.
 */
export function CropMarks({ sheet, trim, bleed, folds }) {
  const left = trim.x;
  const right = trim.x + trim.w;
  const top = trim.y;
  const bottom = trim.y + trim.h;
  const lines = [];
  // Corner marks: from the sheet's edge to the bleed's edge.
  for (const x of [left, right]) {
    lines.push([x, 0, x, top - bleed], [x, bottom + bleed, x, sheet.h]);
  }
  for (const y of [top, bottom]) {
    lines.push([0, y, left - bleed, y], [right + bleed, y, sheet.w, y]);
  }
  for (const x of folds?.x || []) {
    if (Math.abs(x - left) < 0.01 || Math.abs(x - right) < 0.01) continue;
    lines.push([x, 0, x, top - bleed], [x, bottom + bleed, x, sheet.h]);
  }
  for (const y of folds?.y || []) {
    if (Math.abs(y - top) < 0.01 || Math.abs(y - bottom) < 0.01) continue;
    lines.push([0, y, left - bleed, y], [right + bleed, y, sheet.w, y]);
  }
  return (
    <svg
      viewBox={`0 0 ${sheet.w} ${sheet.h}`}
      width={`${sheet.w}mm`}
      height={`${sheet.h}mm`}
      style={{ position: "absolute", left: 0, top: 0, pointerEvents: "none", zIndex: 50 }}
      data-testid="crop-marks"
    >
      {lines
        .filter(([x1, y1, x2, y2]) => Math.hypot(x2 - x1, y2 - y1) > 0.01)
        .map(([x1, y1, x2, y2], i) => (
          <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#000" strokeWidth={LINE_MM} />
        ))}
    </svg>
  );
}
