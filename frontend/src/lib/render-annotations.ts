import type { RoomData } from "@/lib/layout-types";

/** "BEDROOM 1 — 3.6m × 3.2m" — room name + dims, 1 decimal, as drawn onto the
 * annotated R3F capture so the AI-render model has authoritative labels. */
export function roomLabel(room: RoomData): string {
  return `${room.name.toUpperCase()} — ${room.width.toFixed(1)}m × ${room.depth.toFixed(1)}m`;
}

export interface RoomLabelEntry {
  id: string;
  text: string;
  /** World-space label anchor — room centre, in plan (x, y) metres. */
  cx: number;
  cy: number;
  /** Font size hint sized to fit the smaller room dimension. */
  fontSize: number;
}

const MIN_FONT_SIZE = 0.12;
const MAX_FONT_SIZE = 0.32;

/** One label entry per room — the pure data the R3F scene turns into raster
 * <Text> meshes. Kept separate from the scene component so it's unit-testable
 * without a WebGL context. */
export function buildRoomLabels(rooms: RoomData[]): RoomLabelEntry[] {
  return rooms.map((r) => ({
    id: r.id,
    text: roomLabel(r),
    cx: r.x + r.width / 2,
    cy: r.y + r.depth / 2,
    fontSize: Math.min(MAX_FONT_SIZE, Math.max(MIN_FONT_SIZE, Math.min(r.width, r.depth) * 0.12)),
  }));
}

/** "PLOT 12.0m × 9.0m" — overall plot footprint, drawn once at the margin. */
export function plotDimensionLabel(plotWidth: number, plotLength: number): string {
  return `PLOT ${plotWidth.toFixed(1)}m × ${plotLength.toFixed(1)}m`;
}
