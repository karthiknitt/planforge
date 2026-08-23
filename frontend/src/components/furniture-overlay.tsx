"use client";

import type { Fixture, FixtureShape, RoomData } from "@/lib/layout-types";

// Renders a bare <g>, not its own <svg> — a11y is handled by the parent
// FloorPlanSVG's aria-label (floor-plan-svg.tsx), which mentions furniture
// when this overlay is active. Don't add aria attributes here.
//
// The geometry is canonical: FloorDrawing.fixtures (payload v2) carries
// room-relative shapes derived once in the backend (app/engine/furniture.py,
// Task 33) — this component projects them into SVG space and holds NO
// placement logic of its own (the pre-Task-33 local copy was deleted; the
// DXF/ PDF emitters come from the same payload, so the three renderers
// cannot drift).
interface FurnitureOverlayProps {
  rooms: RoomData[];
  fixtures: Fixture[];
  scale: number; // metres → SVG pixels
  offsetX: number; // SVG coordinate origin X (px)
  offsetY: number; // SVG coordinate origin Y (px) — top of plot in SVG space
  plotHeightPx: number; // drawH = plotYExtent * scale, needed for y-flip
}

// Convert metre coords → SVG pixel coords (Y is flipped: metre y=0 is bottom of plot)
function mkPx(offsetX: number, offsetY: number, plotHeightPx: number, scale: number) {
  return {
    px: (x: number) => offsetX + x * scale,
    py: (y: number) => offsetY + plotHeightPx - y * scale,
  };
}

// Reuse the floor-plan's --svg-ink-secondary / --svg-bg tokens (globals.css)
// so furniture outlines/labels and the default silhouette fill stay
// legible/consistent whichever theme the parent FloorPlanSVG is in.
const FURN_STROKE = "var(--svg-ink-secondary)";
const FURN_FILL = "var(--svg-bg)";
const FURN_OPACITY = 0.75;
const FURN_SW = 0.5;

function ArcPath({
  shape,
  room,
  px,
  py,
  scale,
}: {
  shape: FixtureShape;
  room: RoomData;
  px: (v: number) => number;
  py: (v: number) => number;
  scale: number;
}) {
  // DXF convention: centre + radius + CCW degrees in plot space. Endpoints
  // computed in METRES (room-relative + room origin), then run through the
  // y-flip — flipping first would mirror the sweep direction. After the
  // flip a CCW arc renders as CW in screen space, hence sweep-flag 0.
  const a1 = (shape.start_deg * Math.PI) / 180;
  const a2 = (shape.end_deg * Math.PI) / 180;
  const r = shape.radius;
  const p1x = room.x + shape.x + r * Math.cos(a1);
  const p1y = room.y + shape.y + r * Math.sin(a1);
  const p2x = room.x + shape.x + r * Math.cos(a2);
  const p2y = room.y + shape.y + r * Math.sin(a2);
  const extent = (((shape.end_deg - shape.start_deg) % 360) + 360) % 360;
  const largeArc = extent > 180 ? 1 : 0;
  return (
    <path
      d={`M ${px(p1x)} ${py(p1y)} A ${r * scale} ${r * scale} 0 ${largeArc} 0 ${px(p2x)} ${py(p2y)}`}
      fill="none"
    />
  );
}

export function FurnitureOverlay({
  rooms,
  fixtures,
  scale,
  offsetX,
  offsetY,
  plotHeightPx,
}: FurnitureOverlayProps) {
  const { px, py } = mkPx(offsetX, offsetY, plotHeightPx, scale);
  const roomsById = new Map(rooms.map((r) => [r.id, r]));

  return (
    <g
      className="furniture-overlay"
      stroke={FURN_STROKE}
      strokeWidth={FURN_SW}
      opacity={FURN_OPACITY}
      fill={FURN_FILL}
    >
      {fixtures.map((fixture, i) => {
        const room = roomsById.get(fixture.room_id);
        if (!room) return null;
        return (
          <g key={`fx-${fixture.room_id}-${fixture.kind}-${i}`}>
            {fixture.shapes.map((sh) => {
              const x = room.x + sh.x;
              const y = room.y + sh.y;
              const shapeKey = `${sh.kind}:${sh.x},${sh.y},${sh.width}x${sh.depth}r${sh.radius}`;
              switch (sh.kind) {
                case "rect":
                  return (
                    <rect
                      key={shapeKey}
                      x={px(x)}
                      y={py(y + sh.depth)}
                      width={sh.width * scale}
                      height={sh.depth * scale}
                      fill="none"
                      strokeDasharray={sh.dashed ? "3 2" : undefined}
                    />
                  );
                case "circle":
                  return (
                    <circle
                      key={shapeKey}
                      cx={px(x)}
                      cy={py(y)}
                      r={sh.radius * scale}
                      fill="none"
                    />
                  );
                case "line":
                  return (
                    <line
                      key={shapeKey}
                      x1={px(x)}
                      y1={py(y)}
                      x2={px(room.x + sh.x2)}
                      y2={py(room.y + sh.y2)}
                    />
                  );
                case "arc":
                  return (
                    <ArcPath key={shapeKey} shape={sh} room={room} px={px} py={py} scale={scale} />
                  );
                default:
                  return null;
              }
            })}
          </g>
        );
      })}
    </g>
  );
}
