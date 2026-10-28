import React from "react";

// A cover shape: a filled rectangle or circle, or a frame — a double line
// around a box (the Ivory & Gold wedding cover), one element to move,
// resize or recolour as a whole. Its colour is fill_color, like the others.
// Line widths are in cqw (share of the cover's width), so they print the
// same at any size.
const FRAME_LINE = 0.33;
const FRAME_GAP = 1.7;

export function shapeStyle(item, accent) {
  if (item.shape_type === "frame") {
    return { background: "transparent", border: `${FRAME_LINE}cqw solid ${item.fill_color || accent}` };
  }
  return {
    background: item.fill_color || accent,
    borderRadius: item.shape_type === "circle" ? "9999px" : "0",
  };
}

export function ShapeInner({ item, accent }) {
  if (item.shape_type !== "frame") return <div className="w-full h-full pointer-events-none" />;
  return (
    <div
      className="absolute pointer-events-none"
      style={{ inset: `${FRAME_GAP}cqw`, border: `${FRAME_LINE}cqw solid ${item.fill_color || accent}`, opacity: 0.6 }}
    />
  );
}
