const FT_TO_M = 0.3048;
const PAD = 18;
const ROAD_PX = 10;

export interface PlotPreviewInput {
  plotLengthFt: string;
  plotWidthFt: string;
  setbackFrontFt: string;
  setbackRearFt: string;
  setbackLeftFt: string;
  setbackRightFt: string;
  roadSide: string; // "N" | "S" | "E" | "W"
}

export type Box = { x: number; y: number; w: number; h: number };

export interface PlotPreviewGeom {
  valid: boolean;
  viewW: number;
  viewH: number;
  plot: Box | null;
  buildable: Box | null;
  road: Box | null;
}

const num = (s: string): number => {
  const v = Number.parseFloat(s);
  return Number.isFinite(v) ? v : Number.NaN;
};

export function computePlotPreview(
  input: PlotPreviewInput,
  viewW = 260,
  viewH = 260
): PlotPreviewGeom {
  const invalid: PlotPreviewGeom = {
    valid: false,
    viewW,
    viewH,
    plot: null,
    buildable: null,
    road: null,
  };

  const wM = num(input.plotWidthFt) * FT_TO_M;
  const lM = num(input.plotLengthFt) * FT_TO_M;
  if (!(wM > 0) || !(lM > 0)) return invalid;

  const sb = {
    front: Math.max(0, num(input.setbackFrontFt) || 0) * FT_TO_M,
    rear: Math.max(0, num(input.setbackRearFt) || 0) * FT_TO_M,
    left: Math.max(0, num(input.setbackLeftFt) || 0) * FT_TO_M,
    right: Math.max(0, num(input.setbackRightFt) || 0) * FT_TO_M,
  };

  const availW = viewW - 2 * PAD;
  const availH = viewH - 2 * PAD - ROAD_PX;
  const scale = Math.min(availW / wM, availH / lM);

  const plotW = wM * scale;
  const plotH = lM * scale;
  const plot: Box = {
    x: (viewW - plotW) / 2,
    y: (viewH - ROAD_PX - plotH) / 2,
    w: plotW,
    h: plotH,
  };

  // Draw with the road at the roadSide edge. Front setback = road side.
  // Map front/rear/left/right onto screen top/bottom/left/right per roadSide.
  const side = ["N", "S", "E", "W"].includes(input.roadSide) ? input.roadSide : "S";
  const bySide: Record<string, { top: number; bottom: number; left: number; right: number }> = {
    S: { bottom: sb.front, top: sb.rear, left: sb.left, right: sb.right },
    N: { top: sb.front, bottom: sb.rear, left: sb.right, right: sb.left },
    E: { right: sb.front, left: sb.rear, top: sb.left, bottom: sb.right },
    W: { left: sb.front, right: sb.rear, top: sb.right, bottom: sb.left },
  };
  const m = bySide[side];

  const bx = plot.x + m.left * scale;
  const by = plot.y + m.top * scale;
  const bw = plot.w - (m.left + m.right) * scale;
  const bh = plot.h - (m.top + m.bottom) * scale;
  const buildable: Box | null = bw > 1 && bh > 1 ? { x: bx, y: by, w: bw, h: bh } : null;

  const road: Box =
    side === "S"
      ? { x: plot.x, y: plot.y + plot.h + 2, w: plot.w, h: ROAD_PX }
      : side === "N"
        ? { x: plot.x, y: plot.y - ROAD_PX - 2, w: plot.w, h: ROAD_PX }
        : side === "E"
          ? { x: plot.x + plot.w + 2, y: plot.y, w: ROAD_PX, h: plot.h }
          : { x: plot.x - ROAD_PX - 2, y: plot.y, w: ROAD_PX, h: plot.h };

  return { valid: true, viewW, viewH, plot, buildable, road };
}
