// Mirrors the backend's deterministic_layout patterns exactly, so a layout
// picked manually looks identical (proportion-wise) to whatever the AI
// might have generated with the same pattern name.
const M = 0.05;
const USABLE = 1.0 - 2 * M;

export const LAYOUT_PATTERNS = {
  single_full: {
    label: "1 photo",
    slots: [{ x: M, y: M, w: USABLE, h: USABLE }],
  },
  single_centered: {
    label: "1 photo (centered)",
    slots: [{ x: 0.15, y: 0.15, w: 0.7, h: 0.7 }],
  },
  dual_horizontal: {
    label: "2 photos (stacked)",
    slots: [
      { x: M, y: M, w: USABLE, h: (USABLE - 0.04) / 2 },
      { x: M, y: M + (USABLE - 0.04) / 2 + 0.04, w: USABLE, h: (USABLE - 0.04) / 2 },
    ],
  },
  dual_vertical: {
    label: "2 photos (side by side)",
    slots: [
      { x: M, y: M, w: (USABLE - 0.04) / 2, h: USABLE },
      { x: M + (USABLE - 0.04) / 2 + 0.04, y: M, w: (USABLE - 0.04) / 2, h: USABLE },
    ],
  },
  triptych: {
    label: "3 photos",
    slots: [
      { x: M, y: M, w: USABLE * 0.58, h: USABLE },
      { x: M + USABLE * 0.58 + 0.03, y: M, w: USABLE * 0.39, h: (USABLE - 0.03) / 2 },
      { x: M + USABLE * 0.58 + 0.03, y: M + (USABLE - 0.03) / 2 + 0.03, w: USABLE * 0.39, h: (USABLE - 0.03) / 2 },
    ],
  },
  quad_grid: {
    label: "4 photos (grid)",
    slots: [
      { x: M, y: M, w: (USABLE - 0.03) / 2, h: (USABLE - 0.03) / 2 },
      { x: M + (USABLE - 0.03) / 2 + 0.03, y: M, w: (USABLE - 0.03) / 2, h: (USABLE - 0.03) / 2 },
      { x: M, y: M + (USABLE - 0.03) / 2 + 0.03, w: (USABLE - 0.03) / 2, h: (USABLE - 0.03) / 2 },
      { x: M + (USABLE - 0.03) / 2 + 0.03, y: M + (USABLE - 0.03) / 2 + 0.03, w: (USABLE - 0.03) / 2, h: (USABLE - 0.03) / 2 },
    ],
  },
  hero_strip: {
    label: "4 photos (hero + strip)",
    slots: [
      { x: M, y: M, w: USABLE, h: USABLE * 0.62 },
      { x: M, y: M + USABLE * 0.62 + 0.03, w: (USABLE - 0.06) / 3, h: USABLE * 0.35 },
      { x: M + (USABLE - 0.06) / 3 + 0.03, y: M + USABLE * 0.62 + 0.03, w: (USABLE - 0.06) / 3, h: USABLE * 0.35 },
      { x: M + 2 * ((USABLE - 0.06) / 3 + 0.03), y: M + USABLE * 0.62 + 0.03, w: (USABLE - 0.06) / 3, h: USABLE * 0.35 },
    ],
  },
};

export const LAYOUT_GROUPS = [
  { count: 1, patterns: ["single_full", "single_centered"] },
  { count: 2, patterns: ["dual_horizontal", "dual_vertical"] },
  { count: 3, patterns: ["triptych"] },
  { count: 4, patterns: ["quad_grid", "hero_strip"] },
];