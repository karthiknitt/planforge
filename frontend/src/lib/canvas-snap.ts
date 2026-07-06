// Pure snapping math for the canvas editor. Units: metres.
// Grid = internal wall module (115mm); neighbor edges beat grid snaps.

export interface RectMM {
  id: string;
  x: number;
  y: number;
  width: number;
  depth: number;
}

export const GRID_M = 0.115;
export const SNAP_TOL_M = 0.15;

export function snapToGrid(v: number): number {
  return Math.round(v / GRID_M) * GRID_M;
}

export function snapScalar(v: number, candidates: number[], tol: number = SNAP_TOL_M): number {
  let best = v;
  let bestDist = tol;
  for (const c of candidates) {
    const d = Math.abs(c - v);
    if (d <= bestDist) {
      best = c;
      bestDist = d;
    }
  }
  return best;
}

export function edgeCandidates(
  rooms: readonly RectMM[],
  excludeId: string,
  axis: "x" | "y"
): number[] {
  const out: number[] = [];
  for (const r of rooms) {
    if (r.id === excludeId) continue;
    if (axis === "x") out.push(r.x, r.x + r.width);
    else out.push(r.y, r.y + r.depth);
  }
  return out;
}

function snapEdge(v: number, edges: number[]): number {
  // Check for a matching edge by distance, not by comparing snapScalar's
  // result to v — an already-perfectly-aligned coordinate (distance 0)
  // produces a result equal to v too, indistinguishable from "no edge
  // matched" if we only compared the output. That ambiguity let the grid
  // fallback below overwrite an exact neighbor-edge match with a nearby
  // grid multiple (e.g. 1 -> 1.035), silently drifting an already-snapped
  // room by tens of millimetres.
  const matchedEdge = edges.some((e) => Math.abs(e - v) <= SNAP_TOL_M);
  if (matchedEdge) return snapScalar(v, edges);
  const grid = snapToGrid(v);
  return Math.abs(grid - v) <= SNAP_TOL_M ? grid : v;
}

export function snapRect(
  rect: RectMM,
  others: readonly RectMM[],
  plotW: number,
  plotD: number
): RectMM {
  const xEdges = edgeCandidates(others, rect.id, "x");
  const yEdges = edgeCandidates(others, rect.id, "y");

  // try snapping the left edge, then the right edge (keep whichever moved)
  let x = snapEdge(rect.x, xEdges);
  if (x === rect.x) {
    const right = snapEdge(rect.x + rect.width, xEdges);
    if (right !== rect.x + rect.width) x = right - rect.width;
  }
  let y = snapEdge(rect.y, yEdges);
  if (y === rect.y) {
    const top = snapEdge(rect.y + rect.depth, yEdges);
    if (top !== rect.y + rect.depth) y = top - rect.depth;
  }

  x = Math.min(Math.max(0, x), Math.max(0, plotW - rect.width));
  y = Math.min(Math.max(0, y), Math.max(0, plotD - rect.depth));
  return { ...rect, x, y };
}

// Corners named in MODEL space: n = high-y edge (y+depth), s = low-y edge (y),
// w = low-x edge (x), e = high-x edge (x+width). Model y grows away from the
// road; the SVG layer flips it when converting client-pixel deltas to metres.
export type Corner = "nw" | "ne" | "sw" | "se";

export function applyResize(
  rect: RectMM,
  corner: Corner,
  dxM: number,
  dyM: number,
  minSide: number,
  others: readonly RectMM[],
  plotW: number,
  plotD: number
): RectMM {
  const xEdges = edgeCandidates(others, rect.id, "x");
  const yEdges = edgeCandidates(others, rect.id, "y");

  let { x, y, width, depth } = rect;

  if (corner.includes("e")) {
    let right = snapScalar(x + width + dxM, xEdges);
    right = Math.min(right, plotW);
    width = Math.max(minSide, right - x);
  } else {
    let left = snapScalar(x + dxM, xEdges);
    left = Math.max(0, left);
    const right = x + width;
    left = Math.min(left, right - minSide);
    width = right - left;
    x = left;
  }

  if (corner.includes("n")) {
    let top = snapScalar(y + depth + dyM, yEdges);
    top = Math.min(top, plotD);
    depth = Math.max(minSide, top - y);
  } else {
    let bottom = snapScalar(y + dyM, yEdges);
    bottom = Math.max(0, bottom);
    const top = y + depth;
    bottom = Math.min(bottom, top - minSide);
    depth = top - bottom;
    y = bottom;
  }

  return { ...rect, x, y, width, depth };
}
