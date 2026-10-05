/**
 * Spacing guides for moving an item on a page: it snaps to a position where
 *
 * - its margins to the two page edges are equal (centred),
 * - one of its margins equals another item's opposite margin (mirrored
 *   layout: my left margin = your right margin),
 * - the space between it and a neighbour equals a space already on the
 *   page between two items, or equals the space on its other side,
 *
 * and returns little measure marks to draw on the equal spaces.
 *
 * Positions are fractions of the page. One axis at a time: for "x", `pos`
 * and `size` are the item's x and w, `cross` and `crossSize` its y and h.
 */

// How close (fraction of the page) counts as "equal": ~2.5 mm on A4.
export const SPACING_SNAP = 0.012;
const MIN_GAP = 0.004; // touching or overlapping items have no "space" between them

const key = (axis) => (axis === "x" ? ["x", "w", "y", "h"] : ["y", "h", "x", "w"]);

function spansOverlap(a0, a1, b0, b1) {
  return Math.min(a1, b1) - Math.max(a0, b0) > 0;
}

/** Spaces between two items already on the page, along `axis`. */
function existingGaps(others, axis) {
  const [p, s, c, cs] = key(axis);
  const gaps = [];
  for (const a of others) {
    for (const b of others) {
      if (a === b) continue;
      const gap = b[p] - (a[p] + a[s]);
      if (gap < MIN_GAP || !spansOverlap(a[c], a[c] + a[cs], b[c], b[c] + b[cs])) continue;
      const lo = Math.max(a[c], b[c]);
      const hi = Math.min(a[c] + a[cs], b[c] + b[cs]);
      gaps.push({ gap, mark: { axis, from: a[p] + a[s], to: b[p], at: (lo + hi) / 2 } });
    }
  }
  return gaps;
}

/**
 * The spacing snap for one axis: { value, diff, marks } for the closest
 * candidate within SPACING_SNAP, or null.
 */
export function spacingSnap(pos, size, cross, crossSize, others, axis) {
  const [p, s, c, cs] = key(axis);
  const mid = cross + crossSize / 2;
  const candidates = [];
  const add = (value, marks) => {
    if (value < -1e-9 || value + size > 1 + 1e-9) return; // would leave the page
    candidates.push({ value, marks });
  };

  // Centred: equal margins to both page edges.
  {
    const v = (1 - size) / 2;
    add(v, [{ axis, from: 0, to: v, at: mid }, { axis, from: v + size, to: 1, at: mid }]);
  }

  for (const o of others) {
    const oMid = o[c] + o[cs] / 2;
    const oNear = o[p]; // its margin to the start edge
    const oFar = 1 - (o[p] + o[s]); // its margin to the end edge
    // My start margin = its end margin.
    add(oFar, [{ axis, from: 0, to: oFar, at: mid }, { axis, from: o[p] + o[s], to: 1, at: oMid }]);
    // My end margin = its start margin.
    const v = 1 - size - oNear;
    add(v, [{ axis, from: v + size, to: 1, at: mid }, { axis, from: 0, to: oNear, at: oMid }]);
  }

  // Equal spaces between items.
  const near = others.filter((o) => spansOverlap(cross, cross + crossSize, o[c], o[c] + o[cs]));
  const markAt = (o) => (Math.max(cross, o[c]) + Math.min(cross + crossSize, o[c] + o[cs])) / 2;
  const centre = pos + size / 2;
  const before = near.filter((o) => o[p] + o[s] / 2 < centre);
  const after = near.filter((o) => o[p] + o[s] / 2 >= centre);
  for (const { gap, mark } of existingGaps(others, axis)) {
    for (const o of before) {
      const v = o[p] + o[s] + gap;
      add(v, [{ axis, from: o[p] + o[s], to: v, at: markAt(o) }, mark]);
    }
    for (const o of after) {
      const v = o[p] - size - gap;
      add(v, [{ axis, from: v + size, to: o[p], at: markAt(o) }, mark]);
    }
  }
  // Right in the middle of two neighbours: the same space on both sides.
  for (const a of before) {
    for (const b of after) {
      const v = (a[p] + a[s] + b[p] - size) / 2;
      if (v - (a[p] + a[s]) < MIN_GAP) continue;
      add(v, [{ axis, from: a[p] + a[s], to: v, at: markAt(a) }, { axis, from: v + size, to: b[p], at: markAt(b) }]);
    }
  }

  let best = null;
  for (const cand of candidates) {
    const diff = Math.abs(cand.value - pos);
    if (diff < SPACING_SNAP && (!best || diff < best.diff)) best = { ...cand, diff };
  }
  return best;
}
