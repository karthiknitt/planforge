import type { FloorPlanData, RoomData } from "@/lib/layout-types";

// ── Viewport constants ────────────────────────────────────────────────────────
const VP_W = 560;
const VP_H = 680;
const PAD = 36; // padding for labels + road strip
const ROAD_H = 20; // height of the road indicator strip

// ── Room colour palette by type ──────────────────────────────────────────────
const PALETTE: Record<string, { fill: string; stroke: string; text: string }> = {
  living: { fill: "#FEF9C3", stroke: "#CA8A04", text: "#713F12" },
  bedroom: { fill: "#EDE9FE", stroke: "#7C3AED", text: "#3B0764" },
  kitchen: { fill: "#DCFCE7", stroke: "#16A34A", text: "#14532D" },
  toilet: { fill: "#E0F2FE", stroke: "#0284C7", text: "#0C4A6E" },
  staircase: { fill: "#F1F5F9", stroke: "#64748B", text: "#334155" },
  parking: { fill: "#F8FAFC", stroke: "#94A3B8", text: "#475569" },
  utility: { fill: "#F8FAFC", stroke: "#94A3B8", text: "#475569" },
};

const color = (type: string) => PALETTE[type] ?? PALETTE.utility;

// ── North arrow ───────────────────────────────────────────────────────────────
// rotation: S→0° (north up), N→180° (north down), W→90° (north right), E→270° (north left)
const NORTH_ROTATION: Record<string, number> = { S: 0, N: 180, W: 90, E: 270 };

function NorthArrow({ x, y, rotation = 0 }: { x: number; y: number; rotation?: number }) {
  return (
    <g transform={`translate(${x},${y})`}>
      <circle r={14} fill="white" stroke="#94A3B8" strokeWidth={1} />
      <g transform={`rotate(${rotation})`}>
        <polygon points="0,-10 -4,4 0,1 4,4" fill="#1E293B" />
        <text y={-14} textAnchor="middle" fontSize={9} fill="#64748B" fontFamily="sans-serif">
          N
        </text>
      </g>
    </g>
  );
}

// ── Scale bar ─────────────────────────────────────────────────────────────────
function ScaleBar({ x, y, scale }: { x: number; y: number; scale: number }) {
  const barM = 3; // represents 3 metres
  const barPx = barM * scale;
  return (
    <g transform={`translate(${x},${y})`}>
      <line x1={0} y1={0} x2={barPx} y2={0} stroke="#64748B" strokeWidth={2} />
      <line x1={0} y1={-4} x2={0} y2={4} stroke="#64748B" strokeWidth={1.5} />
      <line x1={barPx} y1={-4} x2={barPx} y2={4} stroke="#64748B" strokeWidth={1.5} />
      <text
        x={barPx / 2}
        y={14}
        textAnchor="middle"
        fontSize={9}
        fill="#64748B"
        fontFamily="sans-serif"
      >
        {barM} m
      </text>
    </g>
  );
}

// ── Room label ────────────────────────────────────────────────────────────────
function RoomLabel({
  room,
  px,
  py,
  scale,
}: {
  room: RoomData;
  px: (v: number) => number;
  py: (v: number) => number;
  scale: number;
}) {
  const cx = px(room.x + room.width / 2);
  const cy = py(room.y + room.depth / 2);
  const roomPxW = room.width * scale;
  const roomPxH = room.depth * scale;

  // Skip labels for very small rooms
  if (roomPxW < 28 || roomPxH < 22) return null;

  const fs = Math.max(7, Math.min(11, roomPxW / 8, roomPxH / 4));
  const c = color(room.type);

  const lines = roomPxH >= 44 ? [room.name, `${room.area} m²`] : [`${room.name} · ${room.area}m²`];

  return (
    <g>
      {lines.map((line, i) => (
        <text
          key={line}
          x={cx}
          y={cy + (i - (lines.length - 1) / 2) * (fs + 2)}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={fs}
          fontFamily="sans-serif"
          fontWeight={i === 0 ? "600" : "400"}
          fill={c.text}
        >
          {line}
        </text>
      ))}
    </g>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
interface FloorPlanSVGProps {
  floorPlan: FloorPlanData;
  plotWidth: number;
  plotLength: number;
  roadSide?: string; // "N" | "S" | "E" | "W"
  northDirection?: string;
  className?: string;
}

export function FloorPlanSVG({
  floorPlan,
  plotWidth,
  plotLength,
  roadSide = "S",
  className,
}: FloorPlanSVGProps) {
  const northRotation = NORTH_ROTATION[roadSide] ?? 0;
  // Deduplicate columns by coordinate to avoid duplicate React keys
  const uniqueColumns = Array.from(
    new Map(floorPlan.columns.map((c) => [`${c.x}-${c.y}`, c])).values()
  );
  const availW = VP_W - 2 * PAD;
  const availH = VP_H - 2 * PAD - ROAD_H;

  const scaleX = availW / plotWidth;
  const scaleY = availH / plotLength;
  const scale = Math.min(scaleX, scaleY);

  const drawW = plotWidth * scale;
  const drawH = plotLength * scale;

  // Centre the drawing
  const originX = PAD + (availW - drawW) / 2;
  const originY = PAD + (availH - drawH) / 2;

  // Coordinate transforms (flip y — road is at bottom of SVG)
  const px = (x: number) => originX + x * scale;
  const py = (y: number) => originY + drawH - y * scale;

  return (
    <svg
      viewBox={`0 0 ${VP_W} ${VP_H}`}
      className={className}
      style={{ width: "100%", height: "auto" }}
      aria-label="Floor plan diagram"
    >
      {/* Background */}
      <rect width={VP_W} height={VP_H} fill="#F8FAFC" rx={6} />

      {/* Road strip (always at bottom for simplicity) */}
      <rect
        x={originX}
        y={originY + drawH + 2}
        width={drawW}
        height={ROAD_H}
        fill="#CBD5E1"
        rx={2}
      />
      <text
        x={originX + drawW / 2}
        y={originY + drawH + ROAD_H / 2 + 5}
        textAnchor="middle"
        fontSize={9}
        fontFamily="sans-serif"
        fill="#475569"
        letterSpacing={2}
      >
        ROAD ({roadSide})
      </text>

      {/* Plot boundary */}
      <rect
        x={originX}
        y={originY}
        width={drawW}
        height={drawH}
        fill="white"
        stroke="#CBD5E1"
        strokeWidth={1}
        strokeDasharray="5 3"
      />

      {/* Plot dimension labels */}
      {/* Width label (bottom) */}
      <text
        x={originX + drawW / 2}
        y={originY + drawH + ROAD_H + 18}
        textAnchor="middle"
        fontSize={9}
        fontFamily="sans-serif"
        fill="#94A3B8"
      >
        {plotWidth} m
      </text>
      {/* Depth label (left side) */}
      <text
        x={originX - 8}
        y={originY + drawH / 2}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize={9}
        fontFamily="sans-serif"
        fill="#94A3B8"
        transform={`rotate(-90, ${originX - 8}, ${originY + drawH / 2})`}
      >
        {plotLength} m
      </text>

      {/* Rooms */}
      {floorPlan.rooms.map((room) => {
        const rx = px(room.x);
        const ry = py(room.y + room.depth); // top of rect (y flipped)
        const rw = room.width * scale;
        const rh = room.depth * scale;
        const c = color(room.type);
        return (
          <g key={room.id}>
            <rect
              x={rx}
              y={ry}
              width={rw}
              height={rh}
              fill={c.fill}
              stroke={c.stroke}
              strokeWidth={1.5}
            />
            <RoomLabel room={room} px={px} py={py} scale={scale} />
          </g>
        );
      })}

      {/* Column markers */}
      {uniqueColumns.map((col) => (
        <rect
          key={`${col.x}-${col.y}`}
          x={px(col.x) - 3}
          y={py(col.y) - 3}
          width={6}
          height={6}
          fill="#1E293B"
        />
      ))}

      {/* North arrow */}
      <NorthArrow x={originX + drawW - 2} y={originY + 18} rotation={northRotation} />

      {/* Scale bar */}
      <ScaleBar x={originX + 4} y={originY + drawH - 8} scale={scale} />
    </svg>
  );
}
