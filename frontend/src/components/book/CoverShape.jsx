import React from "react";

// A cover shape: a filled rectangle or circle, or a frame — a double line
// around a box (the Ivory & Gold wedding cover), one element to move,
// resize or recolour as a whole. Its colour is fill_color, like the others.
// Line widths are in cqw (share of the cover's width), so they print the
// same at any size. A frame catches clicks only along its lines: its
// inside stays free for what it surrounds (the names, below it otherwise).
const FRAME_LINE = 0.33;
const FRAME_GAP = 1.7;

export function shapeStyle(item, accent) {
  if (item.shape_type === "frame") {
    return { background: "transparent", border: `${FRAME_LINE}cqw solid ${item.fill_color || accent}`, pointerEvents: "none" };
  }
  return {
    background: item.fill_color || accent,
    borderRadius: item.shape_type === "circle" ? "9999px" : "0",
  };
}

export function ShapeInner({ item, accent }) {
  if (item.shape_type !== "frame") return <div className="w-full h-full pointer-events-none" />;
  // Bands along the four sides, a little wider than the lines (easier to
  // catch), that take the clicks for the frame.
  const band = `${FRAME_GAP + 1}cqw`;
  const edges = [
    { left: 0, right: 0, top: 0, height: band },
    { left: 0, right: 0, bottom: 0, height: band },
    { top: 0, bottom: 0, left: 0, width: band },
    { top: 0, bottom: 0, right: 0, width: band },
  ];
  return (
    <>
      <div
        className="absolute pointer-events-none"
        style={{ inset: `${FRAME_GAP}cqw`, border: `${FRAME_LINE}cqw solid ${item.fill_color || accent}`, opacity: 0.6 }}
      />
      {edges.map((edge, i) => (
        <div key={i} className="absolute pointer-events-auto" style={edge} />
      ))}
    </>
  );
}
