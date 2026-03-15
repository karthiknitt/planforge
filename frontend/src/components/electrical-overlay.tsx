"use client";

import type { RoomData } from "@/lib/layout-types";

interface ElectricalOverlayProps {
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

const ELEC_STROKE = "#f59e0b";
const ELEC_FILL_LIGHT = "#fef3c7";
const ELEC_OPACITY = 0.85;
const ELEC_SW = 1;

// ── Small amber category label ─────────────────────────────────────────────────
function ElecLabel({ x, y, text }: { x: number; y: number; text: string }) {
  return (
    <text
      x={x}
      y={y}
      textAnchor="middle"
      fontSize={4.5}
      fontFamily="sans-serif"
      fill={ELEC_STROKE}
      stroke="none"
    >
      {text}
    </text>
  );
}

// ── Ceiling light point (circle + crosshair) ────────────────────────────────
function CeilingLight({ cx, cy, label }: { cx: number; cy: number; label?: string }) {
  const r = 6;
  return (
    <g stroke={ELEC_STROKE} strokeWidth={ELEC_SW} fill={ELEC_FILL_LIGHT} opacity={ELEC_OPACITY}>
      <circle cx={cx} cy={cy} r={r} />
      <line x1={cx - r} y1={cy} x2={cx + r} y2={cy} />
      <line x1={cx} y1={cy - r} x2={cx} y2={cy + r} />
      {label && <ElecLabel x={cx} y={cy + r + 6} text={label} />}
    </g>
  );
}

// ── Ceiling fan (circle + 4 blade arcs) ────────────────────────────────────
function CeilingFan({ cx, cy }: { cx: number; cy: number }) {
  const r = 8;
  const bladeLen = 10;
  // 4 blades at 0°, 90°, 180°, 270° — drawn as small arcs approximated as short lines
  return (
    <g stroke={ELEC_STROKE} strokeWidth={ELEC_SW} fill="none" opacity={ELEC_OPACITY}>
      <circle cx={cx} cy={cy} r={3} fill={ELEC_FILL_LIGHT} />
      {[0, 90, 180, 270].map((deg) => {
        const rad = (deg * Math.PI) / 180;
        const startR = 4;
        const endR = r + bladeLen * 0.5;
        // Arc approximated as a short curved path
        const x1 = cx + startR * Math.cos(rad);
        const y1 = cy + startR * Math.sin(rad);
        const x2 = cx + endR * Math.cos(rad - 0.35);
        const y2 = cy + endR * Math.sin(rad - 0.35);
        const x3 = cx + endR * Math.cos(rad + 0.35);
        const y3 = cy + endR * Math.sin(rad + 0.35);
        return (
          <path
            key={deg}
            d={`M ${x1} ${y1} Q ${x2} ${y2} ${x3} ${y3}`}
            fill={ELEC_FILL_LIGHT}
            strokeWidth={ELEC_SW}
          />
        );
      })}
      <ElecLabel x={cx} y={cy + r + 14} text="Fan" />
    </g>
  );
}

// ── Switch board (small rect + horizontal lines) ────────────────────────────
function SwitchBoard({ x, y }: { x: number; y: number }) {
  const w = 12;
  const h = 20;
  return (
    <g stroke={ELEC_STROKE} strokeWidth={ELEC_SW} fill={ELEC_FILL_LIGHT} opacity={ELEC_OPACITY}>
      <rect x={x - w / 2} y={y - h / 2} width={w} height={h} />
      {/* 3 switch lines */}
      <line x1={x - w * 0.35} y1={y - h * 0.25} x2={x + w * 0.35} y2={y - h * 0.25} />
      <line x1={x - w * 0.35} y1={y} x2={x + w * 0.35} y2={y} />
      <line x1={x - w * 0.35} y1={y + h * 0.25} x2={x + w * 0.35} y2={y + h * 0.25} />
      <ElecLabel x={x} y={y + h / 2 + 6} text="SW" />
    </g>
  );
}

// ── 5A power socket (rect + 2 circles) ─────────────────────────────────────
function Socket5A({ x, y }: { x: number; y: number }) {
  const w = 10;
  const h = 14;
  return (
    <g stroke={ELEC_STROKE} strokeWidth={ELEC_SW} fill={ELEC_FILL_LIGHT} opacity={ELEC_OPACITY}>
      <rect x={x - w / 2} y={y - h / 2} width={w} height={h} />
      <circle cx={x - 2} cy={y} r={1.8} fill={ELEC_STROKE} />
      <circle cx={x + 2} cy={y} r={1.8} fill={ELEC_STROKE} />
      <ElecLabel x={x} y={y + h / 2 + 6} text="5A" />
    </g>
  );
}

// ── 15A AC socket (rect + 3 holes) ─────────────────────────────────────────
function Socket15A({ x, y }: { x: number; y: number }) {
  const w = 12;
  const h = 16;
  return (
    <g stroke={ELEC_STROKE} strokeWidth={ELEC_SW} fill={ELEC_FILL_LIGHT} opacity={ELEC_OPACITY}>
      <rect x={x - w / 2} y={y - h / 2} width={w} height={h} />
      <circle cx={x - 3} cy={y + 1} r={1.5} fill={ELEC_STROKE} />
      <circle cx={x + 3} cy={y + 1} r={1.5} fill={ELEC_STROKE} />
      <circle cx={x} cy={y - 3} r={1.5} fill={ELEC_STROKE} />
      <ElecLabel x={x} y={y + h / 2 + 6} text="15A AC" />
    </g>
  );
}

// ── MCB distribution panel (rect + grid lines) ─────────────────────────────
function MCBPanel({ x, y }: { x: number; y: number }) {
  const w = 20;
  const h = 30;
  return (
    <g stroke={ELEC_STROKE} strokeWidth={ELEC_SW} fill={ELEC_FILL_LIGHT} opacity={ELEC_OPACITY}>
      <rect x={x - w / 2} y={y - h / 2} width={w} height={h} />
      {/* Grid lines to indicate breakers */}
      <line x1={x - w / 2} y1={y - h * 0.17} x2={x + w / 2} y2={y - h * 0.17} />
      <line x1={x - w / 2} y1={y} x2={x + w / 2} y2={y} />
      <line x1={x - w / 2} y1={y + h * 0.17} x2={x + w / 2} y2={y + h * 0.17} />
      <line x1={x} y1={y - h / 2} x2={x} y2={y + h / 2} />
      <ElecLabel x={x} y={y + h / 2 + 6} text="MCB" />
    </g>
  );
}

// ── Kitchen exhaust fan (circle + diagonal lines) ──────────────────────────
function ExhaustFan({ cx, cy }: { cx: number; cy: number }) {
  const r = 7;
  return (
    <g stroke={ELEC_STROKE} strokeWidth={ELEC_SW} fill={ELEC_FILL_LIGHT} opacity={ELEC_OPACITY}>
      <circle cx={cx} cy={cy} r={r} />
      <line x1={cx - r * 0.7} y1={cy - r * 0.7} x2={cx + r * 0.7} y2={cy + r * 0.7} />
      <line x1={cx + r * 0.7} y1={cy - r * 0.7} x2={cx - r * 0.7} y2={cy + r * 0.7} />
      <ElecLabel x={cx} y={cy + r + 6} text="Exhaust" />
    </g>
  );
}

// ── Geyser 15A point (rect + zigzag line) ──────────────────────────────────
function GeyserPoint({ x, y }: { x: number; y: number }) {
  const w = 12;
  const h = 16;
  // Zigzag (resistance heater symbol) inside rect
  const zx = x - w * 0.3;
  const zy = y - h * 0.2;
  const zw = w * 0.6;
  const zStep = h * 0.15;
  return (
    <g stroke={ELEC_STROKE} strokeWidth={ELEC_SW} fill={ELEC_FILL_LIGHT} opacity={ELEC_OPACITY}>
      <rect x={x - w / 2} y={y - h / 2} width={w} height={h} />
      <polyline
        points={`${zx},${zy + zStep} ${zx + zw * 0.33},${zy} ${zx + zw * 0.66},${zy + zStep} ${zx + zw},${zy}`}
        fill="none"
        strokeWidth={0.8}
      />
      <ElecLabel x={x} y={y + h / 2 + 6} text="Geyser" />
    </g>
  );
}

// ── Per-room electrical symbols ─────────────────────────────────────────────
function RoomElectricalSymbols({
  room,
  px,
  py,
  isFirst,
}: {
  room: RoomData;
  px: (v: number) => number;
  py: (v: number) => number;
  isFirst: boolean;
}) {
  // Room centre in SVG coords
  const cx = px(room.x + room.width / 2);
  const cy = py(room.y + room.depth / 2);

  // Near-door position: left wall, low-y corner in SVG (high y in metre = top in SVG)
  const switchX = px(room.x + 0.15);
  const switchY = py(room.y + room.depth - 0.2);

  // Lower-left corner socket
  const sock1X = px(room.x + 0.15);
  const sock1Y = py(room.y + 0.25);

  // Lower-right corner socket
  const sock2X = px(room.x + room.width - 0.15);
  const sock2Y = py(room.y + 0.25);

  // Upper corner AC socket (top-right in SVG = high x, high y metre)
  const acSockX = px(room.x + room.width - 0.15);
  const acSockY = py(room.y + room.depth - 0.25);

  // MCB panel near entry wall corner (top-left SVG corner = low-x, high-y metre)
  const mcbX = px(room.x + 0.25);
  const mcbY = py(room.y + room.depth - 0.35);

  switch (room.type) {
    case "living": {
      return (
        <g>
          <CeilingLight cx={cx} cy={cy} />
          <CeilingFan cx={cx + 18} cy={cy} />
          {isFirst && <MCBPanel x={mcbX} y={mcbY} />}
          <Socket5A x={sock1X} y={sock1Y} />
          <Socket5A x={sock2X} y={sock2Y} />
          <SwitchBoard x={switchX} y={switchY} />
        </g>
      );
    }
    case "bedroom":
    case "servant_quarter": {
      return (
        <g>
          <CeilingLight cx={cx} cy={cy} />
          <CeilingFan cx={cx} cy={cy + 18} />
          <Socket15A x={acSockX} y={acSockY} />
          <Socket5A x={sock1X} y={sock1Y} />
          <Socket5A x={sock2X} y={sock2Y} />
          <SwitchBoard x={switchX} y={switchY} />
        </g>
      );
    }
    case "master_bedroom": {
      return (
        <g>
          <CeilingLight cx={cx} cy={cy} />
          <CeilingFan cx={cx} cy={cy + 18} />
          <Socket15A x={acSockX} y={acSockY} />
          <Socket5A x={sock1X} y={sock1Y} />
          <Socket5A x={sock2X} y={sock2Y} />
          {/* Extra socket for master bedroom */}
          <Socket5A x={px(room.x + room.width / 2)} y={sock2Y} />
          <SwitchBoard x={switchX} y={switchY} />
        </g>
      );
    }
    case "kitchen": {
      // Exhaust on upper wall (high-y metre = top in SVG)
      const exhaustX = px(room.x + room.width - 0.2);
      const exhaustY = py(room.y + room.depth - 0.2);
      return (
        <g>
          <CeilingLight cx={cx} cy={cy} />
          <ExhaustFan cx={exhaustX} cy={exhaustY} />
          <Socket5A x={sock1X} y={cy} />
          <Socket5A x={sock2X} y={cy} />
          <SwitchBoard x={switchX} y={switchY} />
        </g>
      );
    }
    case "toilet":
    case "bathroom":
    case "wc_only":
    case "bathroom_master": {
      const geysX = px(room.x + room.width - 0.18);
      const geysY = py(room.y + room.depth - 0.25);
      return (
        <g>
          <CeilingLight cx={cx} cy={cy} />
          <GeyserPoint x={geysX} y={geysY} />
          <SwitchBoard x={switchX} y={switchY} />
        </g>
      );
    }
    case "dining": {
      return (
        <g>
          <CeilingLight cx={cx} cy={cy} />
          <CeilingFan cx={cx} cy={cy + 18} />
          <Socket5A x={sock1X} y={sock1Y} />
        </g>
      );
    }
    case "parking":
    case "parking_4w":
    case "parking_2w":
    case "garage": {
      return <CeilingLight cx={cx} cy={cy} label="Parking Light" />;
    }
    case "staircase": {
      // Light at mid-height of stair room
      const stairLightX = px(room.x + room.width / 2);
      const stairLightY = py(room.y + room.depth / 2);
      return <CeilingLight cx={stairLightX} cy={stairLightY} label="Stair Light" />;
    }
    case "home_office":
    case "study": {
      return (
        <g>
          <CeilingLight cx={cx} cy={cy} />
          <Socket5A x={sock1X} y={sock1Y} />
          <Socket5A x={sock2X} y={sock2Y} />
          <SwitchBoard x={switchX} y={switchY} />
        </g>
      );
    }
    default:
      return null;
  }
}

// ── Main exported component ────────────────────────────────────────────────────
export function ElectricalOverlay({
  rooms,
  scale,
  offsetX,
  offsetY,
  plotHeightPx,
}: ElectricalOverlayProps) {
  const { px, py } = mkPx(offsetX, offsetY, plotHeightPx, scale);

  // Track which living room gets the MCB panel (only the first one)
  let livingCount = 0;

  return (
    <g className="electrical-overlay">
      {rooms
        .filter((r) => r.width * scale >= 24 && r.depth * scale >= 24)
        .map((room) => {
          const isFirstLiving = room.type === "living" && livingCount === 0;
          if (room.type === "living") livingCount += 1;
          return (
            <RoomElectricalSymbols
              key={`eo-${room.id}`}
              room={room}
              px={px}
              py={py}
              isFirst={isFirstLiving}
            />
          );
        })}
    </g>
  );
}
