"use client";

import type { RoomData } from "@/lib/layout-types";

interface PlumbingOverlayProps {
  rooms: RoomData[];
  scale: number; // metres → SVG pixels
  offsetX: number; // SVG coordinate origin X (px)
  offsetY: number; // SVG coordinate origin Y (px) — top of plot in SVG space
  plotHeightPx: number; // drawH = plotLength * scale, needed for y-flip
}

// Convert metre coords → SVG pixel coords (Y is flipped: metre y=0 is bottom of plot)
function mkPx(offsetX: number, offsetY: number, plotHeightPx: number, scale: number) {
  return {
    px: (x: number) => offsetX + x * scale,
    py: (y: number) => offsetY + plotHeightPx - y * scale,
  };
}

const SUPPLY_STROKE = "#3b82f6"; // blue for water supply
const DRAIN_STROKE = "#6b7280"; // grey for drain
const PLUMB_OPACITY = 0.8;
const SUPPLY_SW = 1;
const DRAIN_SW = 1.5;

// ── Small blue category label ──────────────────────────────────────────────────
function PlumbLabel({ x, y, text, color }: { x: number; y: number; text: string; color: string }) {
  return (
    <text
      x={x}
      y={y}
      textAnchor="middle"
      fontSize={4.5}
      fontFamily="sans-serif"
      fill={color}
      stroke="none"
    >
      {text}
    </text>
  );
}

// ── Tap / faucet point (circle + T-shape) ─────────────────────────────────────
function TapPoint({ x, y }: { x: number; y: number }) {
  return (
    <g stroke={SUPPLY_STROKE} strokeWidth={SUPPLY_SW} fill="none" opacity={PLUMB_OPACITY}>
      <circle cx={x} cy={y} r={5} fill="#dbeafe" />
      {/* T-shape handle */}
      <line x1={x} y1={y - 5} x2={x} y2={y - 9} />
      <line x1={x - 4} y1={y - 9} x2={x + 4} y2={y - 9} />
      <PlumbLabel x={x} y={y + 11} text="Tap" color={SUPPLY_STROKE} />
    </g>
  );
}

// ── Floor trap (square with X) ────────────────────────────────────────────────
function FloorTrap({ x, y }: { x: number; y: number }) {
  const s = 8;
  return (
    <g stroke={DRAIN_STROKE} strokeWidth={SUPPLY_SW} fill="#f3f4f6" opacity={PLUMB_OPACITY}>
      <rect x={x - s / 2} y={y - s / 2} width={s} height={s} />
      <line x1={x - s / 2} y1={y - s / 2} x2={x + s / 2} y2={y + s / 2} />
      <line x1={x + s / 2} y1={y - s / 2} x2={x - s / 2} y2={y + s / 2} />
      <PlumbLabel x={x} y={y + s / 2 + 6} text="Trap" color={DRAIN_STROKE} />
    </g>
  );
}

// ── Sump / underground tank (rect with diagonal hatch) ────────────────────────
function SumpSymbol({ x, y }: { x: number; y: number }) {
  const w = 20;
  const h = 14;
  return (
    <g stroke={SUPPLY_STROKE} strokeWidth={SUPPLY_SW} fill="#dbeafe" opacity={PLUMB_OPACITY}>
      <rect x={x - w / 2} y={y - h / 2} width={w} height={h} />
      {/* Diagonal hatch lines */}
      <line x1={x - w / 2} y1={y} x2={x} y2={y - h / 2} strokeWidth={0.7} />
      <line x1={x - w / 2} y1={y + h / 2} x2={x + w / 2} y2={y - h / 2} strokeWidth={0.7} />
      <line x1={x} y1={y + h / 2} x2={x + w / 2} y2={y} strokeWidth={0.7} />
      <PlumbLabel x={x} y={y + h / 2 + 7} text="Sump" color={SUPPLY_STROKE} />
    </g>
  );
}

// ── Wet rooms helper ──────────────────────────────────────────────────────────
const WET_TYPES = new Set(["kitchen", "toilet", "bathroom", "wc_only", "bathroom_master"]);

function isWetRoom(type: string): boolean {
  return WET_TYPES.has(type);
}

// ── Supply + drain routing lines ─────────────────────────────────────────────
function PlumbingRoutes({
  rooms,
  px,
  py,
  offsetY,
  plotHeightPx,
}: {
  rooms: RoomData[];
  px: (v: number) => number;
  py: (v: number) => number;
  offsetY: number;
  plotHeightPx: number;
}) {
  const wetRooms = rooms.filter((r) => isWetRoom(r.type));
  if (wetRooms.length < 2) return null;

  // Overhead tank feed: dashed line from top edge of plot to first wet room
  const firstWet = wetRooms[0];
  const ohTankX = px(firstWet.x + firstWet.width / 2);
  const ohTankY = offsetY; // top edge of plot in SVG

  // Sump is rendered separately — here we draw the supply spine
  // Supply line: thin dashed blue line connecting all wet room centres along a horizontal "spine"
  // Spine runs at the mid-height of plot (metre y = average of wet room centres)
  const avgY = wetRooms.reduce((sum, r) => sum + r.y + r.depth / 2, 0) / wetRooms.length;
  const spineY = py(avgY);

  // Draw supply line from OHT feed down to spine, then along spine to each wet room
  const supplyPoints: { x: number; y: number }[] = wetRooms.map((r) => ({
    x: px(r.x + r.width / 2),
    y: py(r.y + r.depth / 2),
  }));

  // Sort supply points by x for a clean routing path
  const sortedSupply = [...supplyPoints].sort((a, b) => a.x - b.x);
  const leftmost = sortedSupply[0];
  const rightmost = sortedSupply[sortedSupply.length - 1];

  // Drain line: dashed grey line from each wet room toward nearest exterior boundary
  // Nearest exterior: bottom of plot (SVG bottom = low metre y = offsetY + plotHeightPx)
  const drainEndY = offsetY + plotHeightPx + 10;

  return (
    <g opacity={PLUMB_OPACITY}>
      {/* Overhead tank feed (blue dashed, from top of plot to first wet room) */}
      <line
        x1={ohTankX}
        y1={ohTankY}
        x2={ohTankX}
        y2={spineY}
        stroke={SUPPLY_STROKE}
        strokeWidth={SUPPLY_SW}
        strokeDasharray="4 3"
      />
      {/* Horizontal supply spine */}
      <line
        x1={leftmost.x}
        y1={spineY}
        x2={rightmost.x}
        y2={spineY}
        stroke={SUPPLY_STROKE}
        strokeWidth={SUPPLY_SW}
        strokeDasharray="4 3"
      />
      {/* Supply drops from spine to each wet room centre */}
      {supplyPoints.map((pt, i) => (
        <line
          // biome-ignore lint/suspicious/noArrayIndexKey: index-stable ordering
          key={`supply-drop-${i}`}
          x1={pt.x}
          y1={spineY}
          x2={pt.x}
          y2={pt.y}
          stroke={SUPPLY_STROKE}
          strokeWidth={SUPPLY_SW}
          strokeDasharray="4 3"
        />
      ))}
      {/* Drain lines from each wet room to exterior bottom boundary */}
      {supplyPoints.map((pt, i) => (
        <line
          // biome-ignore lint/suspicious/noArrayIndexKey: index-stable ordering
          key={`drain-${i}`}
          x1={pt.x}
          y1={pt.y}
          x2={pt.x}
          y2={drainEndY}
          stroke={DRAIN_STROKE}
          strokeWidth={DRAIN_SW}
          strokeDasharray="6 3"
        />
      ))}
      {/* OHT feed label */}
      <text
        x={ohTankX + 4}
        y={ohTankY + 12}
        fontSize={4.5}
        fontFamily="sans-serif"
        fill={SUPPLY_STROKE}
        stroke="none"
        opacity={PLUMB_OPACITY}
      >
        OHT Feed
      </text>
    </g>
  );
}

// ── Per-room plumbing symbols ─────────────────────────────────────────────────
function RoomPlumbingSymbols({
  room,
  px,
  py,
}: {
  room: RoomData;
  px: (v: number) => number;
  py: (v: number) => number;
}) {
  const cx = px(room.x + room.width / 2);
  const cy = py(room.y + room.depth / 2);

  switch (room.type) {
    case "kitchen": {
      // Tap at counter (near lower wall in metre = bottom of kitchen)
      const tapX = px(room.x + room.width - 0.35);
      const tapY = py(room.y + 0.4);
      return (
        <g>
          <TapPoint x={tapX} y={tapY} />
          <FloorTrap x={cx} y={cy + 8} />
        </g>
      );
    }
    case "toilet":
    case "bathroom":
    case "wc_only":
    case "bathroom_master": {
      // Washbasin tap near top-left corner (low x, high y metre = left, top SVG)
      const basinTapX = px(room.x + 0.25);
      const basinTapY = py(room.y + room.depth - 0.4);
      return (
        <g>
          <TapPoint x={basinTapX} y={basinTapY} />
          <FloorTrap x={cx} y={cy} />
        </g>
      );
    }
    default:
      return null;
  }
}

// ── Sump placement (ground floor, low-x low-y corner) ────────────────────────
function SumpPlacement({
  rooms,
  px,
  py,
}: {
  rooms: RoomData[];
  px: (v: number) => number;
  py: (v: number) => number;
}) {
  if (rooms.length === 0) return null;

  // Find the room with smallest x + y (closest to lower-left plot corner)
  const cornerRoom = [...rooms].sort((a, b) => a.x + a.y - (b.x + b.y))[0];
  if (!cornerRoom) return null;

  const sumpX = px(cornerRoom.x + 0.3);
  const sumpY = py(cornerRoom.y + 0.3);

  return <SumpSymbol x={sumpX} y={sumpY} />;
}

// ── Main exported component ────────────────────────────────────────────────────
export function PlumbingOverlay({
  rooms,
  scale,
  offsetX,
  offsetY,
  plotHeightPx,
}: PlumbingOverlayProps) {
  const { px, py } = mkPx(offsetX, offsetY, plotHeightPx, scale);

  const visibleRooms = rooms.filter((r) => r.width * scale >= 24 && r.depth * scale >= 24);

  return (
    <g className="plumbing-overlay">
      {/* Supply + drain routing lines */}
      <PlumbingRoutes
        rooms={visibleRooms}
        px={px}
        py={py}
        offsetY={offsetY}
        plotHeightPx={plotHeightPx}
      />
      {/* Room-level fixtures */}
      {visibleRooms.map((room) => (
        <RoomPlumbingSymbols key={`po-${room.id}`} room={room} px={px} py={py} />
      ))}
      {/* Sump in plot corner */}
      <SumpPlacement rooms={visibleRooms} px={px} py={py} />
    </g>
  );
}
