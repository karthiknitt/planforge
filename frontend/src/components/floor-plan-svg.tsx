import type { FloorPlanData, RoomData } from "@/lib/layout-types";

// ── Viewport constants ────────────────────────────────────────────────────────
const VP_W = 600;
const VP_H = 720;
const PAD = 44; // padding for labels + road strip
const ROAD_H = 22;

// ── Wall thicknesses (metres → will be scaled to px) ─────────────────────────
const EWT = 0.23; // external wall (m)
const IWT = 0.115; // internal wall (m)

// ── Room colour palette ───────────────────────────────────────────────────────
const PALETTE: Record<string, { fill: string; stroke: string; text: string }> = {
  living: { fill: "#FEF9C3", stroke: "#CA8A04", text: "#713F12" },
  bedroom: { fill: "#EDE9FE", stroke: "#7C3AED", text: "#3B0764" },
  kitchen: { fill: "#DCFCE7", stroke: "#16A34A", text: "#14532D" },
  toilet: { fill: "#E0F2FE", stroke: "#0284C7", text: "#0C4A6E" },
  staircase: { fill: "#F1F5F9", stroke: "#64748B", text: "#334155" },
  parking: { fill: "#F8FAFC", stroke: "#94A3B8", text: "#475569" },
  utility: { fill: "#F8FAFC", stroke: "#94A3B8", text: "#475569" },
  pooja: { fill: "#FFF7ED", stroke: "#EA580C", text: "#7C2D12" },
  study: { fill: "#F0FDF4", stroke: "#15803D", text: "#14532D" },
  balcony: { fill: "#F0F9FF", stroke: "#0369A1", text: "#0C4A6E" },
  dining: { fill: "#FEFCE8", stroke: "#A16207", text: "#713F12" },
};

const color = (type: string) => PALETTE[type] ?? PALETTE.utility;

// ── North arrow ───────────────────────────────────────────────────────────────
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
  const barM = 3;
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

// ── Window symbol with W delimiters ───────────────────────────────────────────
function WindowSymbol({
  cx,
  cy,
  width,
  horizontal,
}: {
  cx: number;
  cy: number;
  width: number;
  horizontal: boolean;
}) {
  const gap = 3;
  if (horizontal) {
    return (
      <g>
        <g stroke="#0369A1" strokeWidth={0.8} strokeLinecap="round">
          <line x1={cx - width / 2} y1={cy - gap} x2={cx + width / 2} y2={cy - gap} />
          <line x1={cx - width / 2} y1={cy} x2={cx + width / 2} y2={cy} />
          <line x1={cx - width / 2} y1={cy + gap} x2={cx + width / 2} y2={cy + gap} />
        </g>
        {/* W delimiters */}
        <text
          x={cx - width / 2 - 5}
          y={cy + 3}
          fontSize={6}
          fill="#0369A1"
          fontFamily="sans-serif"
          textAnchor="middle"
          fontWeight="700"
        >
          W
        </text>
        <text
          x={cx + width / 2 + 5}
          y={cy + 3}
          fontSize={6}
          fill="#0369A1"
          fontFamily="sans-serif"
          textAnchor="middle"
          fontWeight="700"
        >
          W
        </text>
      </g>
    );
  }
  return (
    <g>
      <g stroke="#0369A1" strokeWidth={0.8} strokeLinecap="round">
        <line x1={cx - gap} y1={cy - width / 2} x2={cx - gap} y2={cy + width / 2} />
        <line x1={cx} y1={cy - width / 2} x2={cx} y2={cy + width / 2} />
        <line x1={cx + gap} y1={cy - width / 2} x2={cx + gap} y2={cy + width / 2} />
      </g>
      {/* W delimiters */}
      <text
        x={cx}
        y={cy - width / 2 - 4}
        fontSize={6}
        fill="#0369A1"
        fontFamily="sans-serif"
        textAnchor="middle"
        fontWeight="700"
      >
        W
      </text>
      <text
        x={cx}
        y={cy + width / 2 + 8}
        fontSize={6}
        fill="#0369A1"
        fontFamily="sans-serif"
        textAnchor="middle"
        fontWeight="700"
      >
        W
      </text>
    </g>
  );
}

// ── Door symbol (line + quarter-arc + D label) ────────────────────────────────
// wall: "bottom" | "top" | "left" | "right" — which wall edge the door is on
function DoorSymbol({
  hx,
  hy,
  doorPx,
  wall = "bottom",
}: {
  hx: number;
  hy: number;
  doorPx: number;
  wall?: "bottom" | "top" | "left" | "right";
}) {
  const r = doorPx;
  // Door leaf and arc, oriented to the wall
  let leafX2 = hx;
  let leafY2 = hy;
  let arcD = "";
  let labelX = hx;
  let labelY = hy;

  if (wall === "bottom") {
    // hinge at (hx, hy), door leaf goes right, arc sweeps up
    leafX2 = hx + r;
    leafY2 = hy;
    arcD = `M ${hx + r} ${hy} A ${r} ${r} 0 0 0 ${hx} ${hy - r}`;
    labelX = hx + r / 2;
    labelY = hy - r / 2;
  } else if (wall === "top") {
    leafX2 = hx + r;
    leafY2 = hy;
    arcD = `M ${hx + r} ${hy} A ${r} ${r} 0 0 1 ${hx} ${hy + r}`;
    labelX = hx + r / 2;
    labelY = hy + r / 2;
  } else if (wall === "left") {
    leafX2 = hx;
    leafY2 = hy - r;
    arcD = `M ${hx} ${hy - r} A ${r} ${r} 0 0 1 ${hx + r} ${hy}`;
    labelX = hx + r / 2;
    labelY = hy - r / 2;
  } else {
    // right
    leafX2 = hx;
    leafY2 = hy - r;
    arcD = `M ${hx} ${hy - r} A ${r} ${r} 0 0 0 ${hx - r} ${hy}`;
    labelX = hx - r / 2;
    labelY = hy - r / 2;
  }

  return (
    <g stroke="#64748B" strokeWidth={0.75} fill="none">
      <line x1={hx} y1={hy} x2={leafX2} y2={leafY2} />
      <path d={arcD} />
      <text
        x={labelX}
        y={labelY}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize={6}
        fontWeight="700"
        fill="#64748B"
        stroke="none"
        fontFamily="sans-serif"
      >
        D
      </text>
    </g>
  );
}

// ── Dimension line ────────────────────────────────────────────────────────────
function DimLine({
  x1,
  y1,
  x2,
  y2,
  label,
  offset,
  horizontal,
}: {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  label: string;
  offset: number;
  horizontal: boolean;
}) {
  if (horizontal) {
    const dy = y1 - offset;
    return (
      <g stroke="#94A3B8" strokeWidth={0.5} fill="#94A3B8">
        <line x1={x1} y1={y1} x2={x1} y2={dy - 4} />
        <line x1={x2} y1={y1} x2={x2} y2={dy - 4} />
        <line x1={x1} y1={dy} x2={x2} y2={dy} />
        <text
          x={(x1 + x2) / 2}
          y={dy - 6}
          textAnchor="middle"
          fontSize={8}
          fontFamily="sans-serif"
          stroke="none"
        >
          {label}
        </text>
      </g>
    );
  }
  const dx = x1 - offset;
  return (
    <g stroke="#94A3B8" strokeWidth={0.5} fill="#94A3B8">
      <line x1={x1} y1={y1} x2={dx - 4} y2={y1} />
      <line x1={x1} y1={y2} x2={dx - 4} y2={y2} />
      <line x1={dx} y1={y1} x2={dx} y2={y2} />
      <text
        x={dx - 6}
        y={(y1 + y2) / 2}
        textAnchor="middle"
        fontSize={8}
        fontFamily="sans-serif"
        stroke="none"
        transform={`rotate(-90, ${dx - 6}, ${(y1 + y2) / 2})`}
      >
        {label}
      </text>
    </g>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
interface FloorPlanSVGProps {
  floorPlan: FloorPlanData;
  plotWidth: number;
  plotLength: number;
  roadSide?: string;
  northDirection?: string;
  className?: string;
  plotShape?: string;
  plotFrontWidth?: number;
  plotRearWidth?: number;
}

export function FloorPlanSVG({
  floorPlan,
  plotWidth,
  plotLength,
  roadSide = "S",
  className,
  plotShape,
  plotFrontWidth,
  plotRearWidth,
}: FloorPlanSVGProps) {
  const northRotation = NORTH_ROTATION[roadSide] ?? 0;

  const availW = VP_W - 2 * PAD;
  const availH = VP_H - 2 * PAD - ROAD_H;

  const scaleX = availW / plotWidth;
  const scaleY = availH / plotLength;
  const scale = Math.min(scaleX, scaleY);

  const drawW = plotWidth * scale;
  const drawH = plotLength * scale;

  const originX = PAD + (availW - drawW) / 2;
  const originY = PAD + (availH - drawH) / 2;

  // Coordinate transforms (flip y — road at bottom)
  const px = (x: number) => originX + x * scale;
  const py = (y: number) => originY + drawH - y * scale;

  const rooms = floorPlan.rooms;

  // Compute building extents for wall rendering
  const minX = rooms.length ? Math.min(...rooms.map((r) => r.x)) : 0;
  const maxX = rooms.length ? Math.max(...rooms.map((r) => r.x + r.width)) : 0;
  const minY = rooms.length ? Math.min(...rooms.map((r) => r.y)) : 0;
  const maxY = rooms.length ? Math.max(...rooms.map((r) => r.y + r.depth)) : 0;

  // Internal wall x/y grid lines (exclude outer edges)
  const wallXs = [...new Set(rooms.flatMap((r) => [r.x, r.x + r.width]))].sort((a, b) => a - b);
  const wallYs = [...new Set(rooms.flatMap((r) => [r.y, r.y + r.depth]))].sort((a, b) => a - b);
  const intWallXs = wallXs.slice(1, -1);
  const intWallYs = wallYs.slice(1, -1);

  // Windows on exterior-facing room walls
  const habitable = new Set(["living", "bedroom", "kitchen", "study", "dining"]);
  const winPx = Math.min(1.2, plotWidth * 0.15) * scale;
  const tol = 0.05;

  const uniqueCols = Array.from(
    new Map(floorPlan.columns.map((c) => [`${c.x}-${c.y}`, c])).values()
  );

  const halfEwt = (EWT * scale) / 2;
  const halfIwt = (IWT * scale) / 2;

  // Building boundary in SVG coords
  const bLeft = px(minX);
  const bRight = px(maxX);
  const bBottom = py(minY);
  const bTop = py(maxY);

  return (
    <svg
      viewBox={`0 0 ${VP_W} ${VP_H}`}
      className={className}
      style={{ width: "100%", height: "auto" }}
      aria-label="Floor plan diagram"
    >
      {/* Background */}
      <rect width={VP_W} height={VP_H} fill="#F8FAFC" rx={6} />

      {/* Road strip */}
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

      {/* Plot boundary (dashed) */}
      {plotShape === "trapezoid" && plotFrontWidth && plotRearWidth ? (
        (() => {
          const fw = plotFrontWidth * scale;
          const rw = plotRearWidth * scale;
          const fOffset = originX + (drawW - fw) / 2;
          const rOffset = originX + (drawW - rw) / 2;
          const points = [
            `${fOffset},${originY + drawH}`,
            `${fOffset + fw},${originY + drawH}`,
            `${rOffset + rw},${originY}`,
            `${rOffset},${originY}`,
          ].join(" ");
          return (
            <polygon
              points={points}
              fill="white"
              stroke="#CBD5E1"
              strokeWidth={1}
              strokeDasharray="5 3"
            />
          );
        })()
      ) : (
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
      )}

      {/* ── Room fills ─────────────────────────────────────────────────── */}
      {rooms.map((room) => {
        const rx = px(room.x);
        const ry = py(room.y + room.depth);
        const rw = room.width * scale;
        const rh = room.depth * scale;
        return (
          <rect key={room.id} x={rx} y={ry} width={rw} height={rh} fill={color(room.type).fill} />
        );
      })}

      {/* ── Internal wall double-lines ─────────────────────────────────── */}
      {rooms.length > 0 && (
        <g stroke="#334155" strokeWidth={0.8}>
          {intWallXs.map((x) => {
            const svgX = px(x);
            return (
              <g key={`vw-${x}`}>
                <line x1={svgX - halfIwt} y1={bBottom} x2={svgX - halfIwt} y2={bTop} />
                <line x1={svgX + halfIwt} y1={bBottom} x2={svgX + halfIwt} y2={bTop} />
              </g>
            );
          })}
          {intWallYs.map((y) => {
            const svgY = py(y);
            return (
              <g key={`hw-${y}`}>
                <line x1={bLeft} y1={svgY - halfIwt} x2={bRight} y2={svgY - halfIwt} />
                <line x1={bLeft} y1={svgY + halfIwt} x2={bRight} y2={svgY + halfIwt} />
              </g>
            );
          })}
        </g>
      )}

      {/* ── External walls (outer + inner line) ───────────────────────── */}
      {rooms.length > 0 && (
        <g stroke="#1E293B" fill="none">
          <rect
            x={bLeft - halfEwt}
            y={bTop - halfEwt}
            width={bRight - bLeft + 2 * halfEwt}
            height={bBottom - bTop + 2 * halfEwt}
            strokeWidth={2}
          />
          <rect
            x={bLeft + halfEwt}
            y={bTop + halfEwt}
            width={bRight - bLeft - 2 * halfEwt}
            height={bBottom - bTop - 2 * halfEwt}
            strokeWidth={0.8}
          />
        </g>
      )}

      {/* ── Window symbols on exterior walls ──────────────────────────── */}
      {rooms
        .filter((r) => habitable.has(r.type))
        .flatMap((room) => {
          const symbols = [];
          const cx_m = room.x + room.width / 2;
          const cy_m = room.y + room.depth / 2;

          if (Math.abs(room.y - minY) < tol) {
            symbols.push(
              <WindowSymbol
                key={`w-front-${room.id}`}
                cx={px(cx_m)}
                cy={py(room.y)}
                width={winPx}
                horizontal
              />
            );
          }
          if (Math.abs(room.y + room.depth - maxY) < tol) {
            symbols.push(
              <WindowSymbol
                key={`w-rear-${room.id}`}
                cx={px(cx_m)}
                cy={py(room.y + room.depth)}
                width={winPx}
                horizontal
              />
            );
          }
          if (Math.abs(room.x - minX) < tol) {
            symbols.push(
              <WindowSymbol
                key={`w-left-${room.id}`}
                cx={px(room.x)}
                cy={py(cy_m)}
                width={winPx}
                horizontal={false}
              />
            );
          }
          if (Math.abs(room.x + room.width - maxX) < tol) {
            symbols.push(
              <WindowSymbol
                key={`w-right-${room.id}`}
                cx={px(room.x + room.width)}
                cy={py(cy_m)}
                width={winPx}
                horizontal={false}
              />
            );
          }
          return symbols;
        })}

      {/* ── Door symbols ──────────────────────────────────────────────── */}
      {rooms
        .filter((r) => habitable.has(r.type) || r.type === "utility")
        .map((room) => {
          const doorPx = Math.min(0.9 * scale, room.width * scale * 0.4);
          // Place door on the wall that faces an adjacent room or exterior
          // Prefer bottom wall (road-facing / front), else top
          const onBottom = Math.abs(room.y - minY) < tol;
          const onTop = Math.abs(room.y + room.depth - maxY) < tol;
          const onLeft = Math.abs(room.x - minX) < tol;

          let wall: "bottom" | "top" | "left" | "right" = "bottom";
          let hx: number;
          let hy: number;

          if (onBottom) {
            wall = "bottom";
            hx = px(room.x + 0.1);
            hy = py(room.y);
          } else if (onTop) {
            wall = "top";
            hx = px(room.x + 0.1);
            hy = py(room.y + room.depth);
          } else if (onLeft) {
            wall = "left";
            hx = px(room.x);
            hy = py(room.y + room.depth - 0.1);
          } else {
            wall = "right";
            hx = px(room.x + room.width);
            hy = py(room.y + room.depth - 0.1);
          }

          return <DoorSymbol key={`d-${room.id}`} hx={hx} hy={hy} doorPx={doorPx} wall={wall} />;
        })}

      {/* ── Column markers ────────────────────────────────────────────── */}
      {uniqueCols.map((col) => {
        const colPx = Math.max(4, 0.3 * scale);
        return (
          <rect
            key={`col-${col.x}-${col.y}`}
            x={px(col.x) - colPx / 2}
            y={py(col.y) - colPx / 2}
            width={colPx}
            height={colPx}
            fill="#1E293B"
          />
        );
      })}

      {/* ── Room labels ───────────────────────────────────────────────── */}
      {rooms.map((room) => (
        <RoomLabel key={`lbl-${room.id}`} room={room} px={px} py={py} scale={scale} />
      ))}

      {/* ── Internal room dimensions ──────────────────────────────────── */}
      {rooms.map((room) => {
        const roomPxW = room.width * scale;
        const roomPxH = room.depth * scale;
        if (roomPxW < 40 || roomPxH < 40) return null;

        const cx = px(room.x + room.width / 2);
        const cy = py(room.y + room.depth / 2);
        const fs = Math.max(6, Math.min(8, roomPxW / 10));
        // Place dimension text slightly below the room name
        const offsetY = roomPxH >= 44 ? fs * 3.5 : fs * 2.2;

        return (
          <text
            key={`dim-${room.id}`}
            x={cx}
            y={cy + offsetY}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize={fs}
            fontFamily="sans-serif"
            fill={color(room.type).text}
            opacity={0.7}
          >
            {room.width.toFixed(1)} × {room.depth.toFixed(1)} m
          </text>
        );
      })}

      {/* ── Dimension lines ───────────────────────────────────────────── */}
      <DimLine
        x1={originX}
        y1={originY + drawH}
        x2={originX + drawW}
        y2={originY + drawH}
        label={`${plotWidth} m`}
        offset={-28}
        horizontal
      />
      <DimLine
        x1={originX}
        y1={originY}
        x2={originX}
        y2={originY + drawH}
        label={`${plotLength} m`}
        offset={-28}
        horizontal={false}
      />

      {/* ── North arrow ───────────────────────────────────────────────── */}
      <NorthArrow x={originX + drawW - 2} y={originY + 18} rotation={northRotation} />

      {/* ── Scale bar ─────────────────────────────────────────────────── */}
      <ScaleBar x={originX + 4} y={originY + drawH - 10} scale={scale} />
    </svg>
  );
}
