import { useRef, useState } from "react";
import { ElectricalOverlay } from "@/components/electrical-overlay";
import { FurnitureOverlay } from "@/components/furniture-overlay";
import { PlumbingOverlay } from "@/components/plumbing-overlay";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { FloorPlanData, RoomData } from "@/lib/layout-types";
import type { Locale } from "@/lib/locale-context";
import { getRoomName } from "@/lib/room-names";

// ── Annotation data structure ─────────────────────────────────────────────────
export interface Annotation {
  room_id: string;
  room_name: string;
  note: string;
  x: number;
  y: number;
}

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
  master_bedroom: { fill: "#F3E8FF", stroke: "#9333EA", text: "#3B0764" },
  kitchen: { fill: "#DCFCE7", stroke: "#16A34A", text: "#14532D" },
  toilet: { fill: "#E0F2FE", stroke: "#0284C7", text: "#0C4A6E" },
  wc_only: { fill: "#BAE6FD", stroke: "#0284C7", text: "#0C4A6E" },
  bathroom_master: { fill: "#BFDBFE", stroke: "#1D4ED8", text: "#1E3A8A" },
  staircase: { fill: "#F1F5F9", stroke: "#64748B", text: "#334155" },
  parking: { fill: "#F8FAFC", stroke: "#94A3B8", text: "#475569" },
  parking_4w: { fill: "#F1F5F9", stroke: "#64748B", text: "#334155" },
  parking_2w: { fill: "#E7E5E4", stroke: "#78716C", text: "#44403C" },
  utility: { fill: "#F8FAFC", stroke: "#94A3B8", text: "#475569" },
  pooja: { fill: "#FFF7ED", stroke: "#EA580C", text: "#7C2D12" },
  study: { fill: "#F0FDF4", stroke: "#15803D", text: "#14532D" },
  balcony: { fill: "#F0F9FF", stroke: "#0369A1", text: "#0C4A6E" },
  dining: { fill: "#FEFCE8", stroke: "#A16207", text: "#713F12" },
  // Phase C — new room types
  servant_quarter: { fill: "#FFF7ED", stroke: "#EA580C", text: "#7C2D12" },
  home_office: { fill: "#F0FDF4", stroke: "#15803D", text: "#14532D" },
  gym: { fill: "#FFF1F2", stroke: "#E11D48", text: "#881337" },
  store_room: { fill: "#F8FAFC", stroke: "#94A3B8", text: "#475569" },
  garage: { fill: "#F0F9FF", stroke: "#0369A1", text: "#0C4A6E" },
  passage: { fill: "#F1F5F9", stroke: "#64748B", text: "#334155" },
  open_terrace: { fill: "#F0F9FF", stroke: "#0369A1", text: "#0C4A6E" },
};

const color = (type: string) => PALETTE[type] ?? PALETTE.utility;

// ── North arrow ───────────────────────────────────────────────────────────────
const NORTH_ROTATION: Record<string, number> = { S: 0, N: 180, W: 90, E: 270 };

function NorthArrow({ x, y, rotation = 0 }: { x: number; y: number; rotation?: number }) {
  return (
    <g transform={`translate(${x},${y})`}>
      <circle r={14} fill="white" stroke="#94A3B8" strokeWidth={1} className="svg-north-circle" />
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
  locale = "en",
}: {
  room: RoomData;
  px: (v: number) => number;
  py: (v: number) => number;
  scale: number;
  locale?: Locale;
}) {
  const cx = px(room.x + room.width / 2);
  const cy = py(room.y + room.depth / 2);
  const roomPxW = room.width * scale;
  const roomPxH = room.depth * scale;

  if (roomPxW < 28 || roomPxH < 22) return null;

  const fs = Math.max(7, Math.min(11, roomPxW / 8, roomPxH / 4));
  const c = color(room.type);
  const displayName = getRoomName(room.type, locale);
  const lines =
    roomPxH >= 44 ? [displayName, `${room.area} m²`] : [`${displayName} · ${room.area}m²`];

  return (
    <g>
      {lines.map((line, lineIdx) => (
        <text
          key={line}
          x={cx}
          y={cy + (lineIdx - (lines.length - 1) / 2) * (fs + 2)}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={fs}
          fontFamily="sans-serif"
          fontWeight={lineIdx === 0 ? "600" : "400"}
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

// ── Staircase treads ──────────────────────────────────────────────────────────
function StaircaseSymbol({
  room,
  px,
  py,
  scale,
}: {
  room: { x: number; y: number; width: number; depth: number };
  px: (v: number) => number;
  py: (v: number) => number;
  scale: number;
}) {
  const x0 = px(room.x);
  const x1 = px(room.x + room.width);
  const y0 = py(room.y + room.depth); // top in SVG (y flipped)
  const y1 = py(room.y); // bottom in SVG
  const h = Math.abs(y1 - y0);
  const treadH = Math.max(4, Math.min(10, scale * 0.3));
  const numTreads = Math.max(3, Math.floor(h / treadH));
  const step = h / numTreads;

  const lines: React.ReactNode[] = [];
  for (let i = 1; i < numTreads; i++) {
    const ly = y0 + i * step;
    lines.push(<line key={i} x1={x0} y1={ly} x2={x1} y2={ly} stroke="#94A3B8" strokeWidth={0.6} />);
  }
  // Cut line (diagonal cross-hatching line with UP arrow)
  const midY = (y0 + y1) / 2;
  return (
    <g>
      {lines}
      {/* Cut line */}
      <line
        x1={x0}
        y1={midY}
        x2={x1}
        y2={midY}
        stroke="#64748B"
        strokeWidth={1.2}
        strokeDasharray="4 2"
      />
      {/* UP label */}
      <text
        x={(x0 + x1) / 2}
        y={midY - 4}
        textAnchor="middle"
        fontSize={Math.max(6, scale * 0.12)}
        fontFamily="sans-serif"
        fill="#64748B"
        fontWeight="600"
      >
        UP
      </text>
    </g>
  );
}

// ── Furniture symbols (SVG equivalents of DXF cad_advanced.py) ────────────────

function FurnitureBed({
  room,
  px,
  py,
  scale,
  isMaster,
}: {
  room: { x: number; y: number; width: number; depth: number };
  px: (v: number) => number;
  py: (v: number) => number;
  scale: number;
  isMaster: boolean;
}) {
  const margin = 0.15;
  const bedW = Math.min(isMaster ? 1.8 : 1.2, room.width - 2 * margin);
  const bedD = Math.min(2.0, room.depth - margin);
  if (bedW < 0.5 || bedD < 0.5) return null;

  const bx = room.x + (room.width - bedW) / 2;
  const by = room.y + room.depth - margin - bedD;
  const rx = px(bx);
  const ry = py(by + bedD);
  const rw = bedW * scale;
  const rh = bedD * scale;

  return (
    <g stroke="#7C3AED" strokeWidth={0.7} fill="none" opacity={0.7}>
      <rect x={rx} y={ry} width={rw} height={rh} />
      {/* Headboard */}
      <rect x={rx} y={ry} width={rw} height={0.1 * scale} fill="#7C3AED" opacity={0.3} />
      {/* Pillow arc */}
      <path
        d={`M ${rx + rw / 2 - Math.min(0.35, bedW / 3) * scale} ${ry + 0.25 * scale}
            A ${Math.min(0.35, bedW / 3) * scale} ${0.15 * scale} 0 0 1
            ${rx + rw / 2 + Math.min(0.35, bedW / 3) * scale} ${ry + 0.25 * scale}`}
        strokeLinecap="round"
      />
    </g>
  );
}

function FurnitureLiving({
  room,
  px,
  py,
  scale,
}: {
  room: { x: number; y: number; width: number; depth: number };
  px: (v: number) => number;
  py: (v: number) => number;
  scale: number;
}) {
  const margin = 0.2;
  const sofaW = Math.min(2.4, room.width - 2 * margin);
  const sofaD = 0.9;
  if (sofaW < 1.0) return null;

  const sx = room.x + (room.width - sofaW) / 2;
  const sy = room.y + room.depth - margin - sofaD;
  const tvW = Math.min(1.8, room.width - 2 * margin);
  const tvX = room.x + (room.width - tvW) / 2;

  return (
    <g stroke="#CA8A04" strokeWidth={0.7} fill="none" opacity={0.7}>
      {/* Sofa body */}
      <rect x={px(sx)} y={py(sy + sofaD)} width={sofaW * scale} height={sofaD * scale} />
      {/* Armrests */}
      <rect
        x={px(sx)}
        y={py(sy + sofaD)}
        width={0.3 * scale}
        height={sofaD * scale}
        fill="#CA8A04"
        fillOpacity={0.15}
      />
      <rect
        x={px(sx + sofaW - 0.3)}
        y={py(sy + sofaD)}
        width={0.3 * scale}
        height={sofaD * scale}
        fill="#CA8A04"
        fillOpacity={0.15}
      />
      {/* TV unit */}
      <rect
        x={px(tvX)}
        y={py(room.y + margin + 0.4)}
        width={tvW * scale}
        height={0.4 * scale}
        fill="#CA8A04"
        fillOpacity={0.1}
      />
    </g>
  );
}

function FurnitureDining({
  room,
  px,
  py,
  scale,
}: {
  room: { x: number; y: number; width: number; depth: number };
  px: (v: number) => number;
  py: (v: number) => number;
  scale: number;
}) {
  const margin = 0.4;
  const tW = Math.min(1.8, room.width - 2 * margin);
  const tD = Math.min(0.9, room.depth - 2 * margin);
  if (tW < 0.8 || tD < 0.5) return null;

  const tx = room.x + (room.width - tW) / 2;
  const ty = room.y + (room.depth - tD) / 2;
  const chairR = 0.22 * scale;
  const gap = 0.08 * scale;
  const numChairs = tW >= 1.5 ? 3 : 2;

  const chairs: React.ReactNode[] = [];
  for (let i = 0; i < numChairs; i++) {
    const cxVal = px(tx + (tW / (numChairs + 1)) * (i + 1));
    chairs.push(
      <circle key={`b${i}`} cx={cxVal} cy={py(ty) + gap + chairR} r={chairR} />,
      <circle key={`t${i}`} cx={cxVal} cy={py(ty + tD) - gap - chairR} r={chairR} />
    );
  }

  return (
    <g stroke="#A16207" strokeWidth={0.7} fill="none" opacity={0.7}>
      <rect x={px(tx)} y={py(ty + tD)} width={tW * scale} height={tD * scale} />
      {chairs}
      <circle cx={px(tx) - gap - chairR} cy={py(ty + tD / 2)} r={chairR} />
      <circle cx={px(tx + tW) + gap + chairR} cy={py(ty + tD / 2)} r={chairR} />
    </g>
  );
}

function FurnitureKitchen({
  room,
  px,
  py,
  scale,
}: {
  room: { x: number; y: number; width: number; depth: number };
  px: (v: number) => number;
  py: (v: number) => number;
  scale: number;
}) {
  const margin = 0.05;
  const cw = 0.6;
  if (room.width < 1.2 || room.depth < 1.2) return null;

  const rx = room.x;
  const ry = room.y;
  const rw = room.width;
  const rd = room.depth;
  const rearY = ry + rd - margin - cw;
  const leftLen = rd - 2 * margin - cw;

  return (
    <g stroke="#16A34A" strokeWidth={0.7} fill="none" opacity={0.7}>
      {/* Rear counter */}
      <rect
        x={px(rx + margin)}
        y={py(rearY + cw)}
        width={(rw - 2 * margin) * scale}
        height={cw * scale}
        fill="#16A34A"
        fillOpacity={0.1}
      />
      {/* Left counter */}
      {leftLen > 0.5 && (
        <rect
          x={px(rx + margin)}
          y={py(ry + margin + leftLen)}
          width={cw * scale}
          height={leftLen * scale}
          fill="#16A34A"
          fillOpacity={0.1}
        />
      )}
      {/* Sink circle */}
      <circle
        cx={px(rx + margin + (rw - 2 * margin) - 0.65 + 0.275)}
        cy={py(rearY + cw / 2)}
        r={0.18 * scale}
      />
      {/* Stove burners */}
      {[
        [rx + margin + 0.1 + Math.min(0.6, (rw - 2 * margin) * 0.4) * 0.3, rearY + cw * 0.3],
        [rx + margin + 0.1 + Math.min(0.6, (rw - 2 * margin) * 0.4) * 0.7, rearY + cw * 0.3],
      ].map(([bx, by]) => (
        <circle key={`burner-${bx}-${by}`} cx={px(bx)} cy={py(by)} r={0.07 * scale} />
      ))}
    </g>
  );
}

function FurnitureToilet({
  room,
  px,
  py,
  scale,
}: {
  room: { x: number; y: number; width: number; depth: number };
  px: (v: number) => number;
  py: (v: number) => number;
  scale: number;
}) {
  const margin = 0.08;
  if (room.width < 0.8 || room.depth < 0.8) return null;

  const rx = room.x;
  const ry = room.y;
  const rw = room.width;
  const rd = room.depth;
  const wcCx = rx + margin + 0.2;
  const wcCy = ry + rd - margin - 0.15;
  const r = 0.18 * scale;

  return (
    <g stroke="#0284C7" strokeWidth={0.7} fill="none" opacity={0.7}>
      {/* WC tank */}
      <rect
        x={px(wcCx - 0.175)}
        y={py(wcCy + 0.15)}
        width={0.35 * scale}
        height={0.15 * scale}
        fill="#0284C7"
        fillOpacity={0.15}
      />
      {/* WC bowl arc */}
      <path
        d={`M ${px(wcCx) - r} ${py(wcCy)} A ${r} ${r} 0 0 0 ${px(wcCx) + r} ${py(wcCy)}`}
        strokeLinecap="round"
      />
      <line x1={px(wcCx) - r} y1={py(wcCy)} x2={px(wcCx) + r} y2={py(wcCy)} />
      {/* Basin */}
      <circle cx={px(rx + rw - margin - 0.2)} cy={py(ry + margin + 0.2)} r={0.18 * scale} />
    </g>
  );
}

function FurnitureBathtub({
  room,
  px,
  py,
  scale,
}: {
  room: { x: number; y: number; width: number; depth: number };
  px: (v: number) => number;
  py: (v: number) => number;
  scale: number;
}) {
  // Bathtub: 1.7 m × 0.75 m, placed along the longest wall
  const tubL = Math.min(1.7, room.width - 0.3);
  const tubW = Math.min(0.75, room.depth * 0.45);
  if (tubL < 0.8 || tubW < 0.3) return null;
  // Place along the top wall (rear)
  const tx = room.x + (room.width - tubL) / 2;
  const ty = room.y + room.depth - tubW - 0.1;
  const rx = px(tx);
  const ry = py(ty + tubW);
  const tw = tubL * scale;
  const th = tubW * scale;
  const rr = Math.min(tw, th) * 0.35; // corner radius for rounded tub
  return (
    <g stroke="#1D4ED8" strokeWidth={0.8} fill="#DBEAFE" opacity={0.7}>
      <rect x={rx} y={ry} width={tw} height={th} rx={rr} ry={rr} />
      {/* tap end indicator */}
      <circle cx={rx + tw * 0.5} cy={ry + th * 0.15} r={Math.min(tw, th) * 0.1} fill="#1D4ED8" />
    </g>
  );
}

function FurnitureParking({
  room,
  px,
  py,
  scale,
  is2w = false,
}: {
  room: { x: number; y: number; width: number; depth: number };
  px: (v: number) => number;
  py: (v: number) => number;
  scale: number;
  is2w?: boolean;
}) {
  const margin = 0.2;
  if (is2w) {
    // 2-wheeler: 1.0 m × 2.2 m silhouette
    const bW = Math.min(0.8, room.width - 2 * margin);
    const bD = Math.min(2.0, room.depth - 2 * margin);
    if (bW < 0.3 || bD < 0.5) return null;
    const bx = room.x + (room.width - bW) / 2;
    const by = room.y + (room.depth - bD) / 2;
    return (
      <g stroke="#78716C" strokeWidth={0.7} fill="none" opacity={0.6}>
        <ellipse
          cx={px(bx + bW / 2)}
          cy={py(by + bD / 2)}
          rx={(bW / 2) * scale}
          ry={(bD / 2) * scale}
          strokeDasharray="3 2"
        />
        {/* wheel marks */}
        <line
          x1={px(bx + bW / 2)}
          y1={py(by + bD * 0.15)}
          x2={px(bx + bW / 2)}
          y2={py(by + bD * 0.85)}
          strokeWidth={1.2}
        />
      </g>
    );
  }
  const carW = Math.min(2.0, room.width - 2 * margin);
  const carD = Math.min(4.5, room.depth - 2 * margin);
  if (carW < 0.5 || carD < 0.5) return null;

  const cx = room.x + (room.width - carW) / 2;
  const cy = room.y + (room.depth - carD) / 2;

  return (
    <g stroke="#94A3B8" strokeWidth={0.7} fill="none" opacity={0.6}>
      <rect
        x={px(cx)}
        y={py(cy + carD)}
        width={carW * scale}
        height={carD * scale}
        strokeDasharray="3 2"
      />
    </g>
  );
}

function RoomFurniture({
  room,
  px,
  py,
  scale,
}: {
  room: { x: number; y: number; width: number; depth: number; type: string };
  px: (v: number) => number;
  py: (v: number) => number;
  scale: number;
}) {
  switch (room.type) {
    case "bedroom":
      return <FurnitureBed room={room} px={px} py={py} scale={scale} isMaster={false} />;
    case "master_bedroom":
      return <FurnitureBed room={room} px={px} py={py} scale={scale} isMaster={true} />;
    case "living":
      return <FurnitureLiving room={room} px={px} py={py} scale={scale} />;
    case "dining":
      return <FurnitureDining room={room} px={px} py={py} scale={scale} />;
    case "kitchen":
      return <FurnitureKitchen room={room} px={px} py={py} scale={scale} />;
    case "toilet":
    case "wc_only":
      return <FurnitureToilet room={room} px={px} py={py} scale={scale} />;
    case "bathroom_master":
      return (
        <g>
          <FurnitureToilet room={room} px={px} py={py} scale={scale} />
          <FurnitureBathtub room={room} px={px} py={py} scale={scale} />
        </g>
      );
    case "parking":
    case "parking_4w":
    case "garage":
      return <FurnitureParking room={room} px={px} py={py} scale={scale} is2w={false} />;
    case "parking_2w":
      return <FurnitureParking room={room} px={px} py={py} scale={scale} is2w={true} />;
    default:
      return null;
  }
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

// ── Minimum room side dimensions for edit-mode constraint enforcement ─────────
const MIN_ROOM_SIDE: Record<string, number> = {
  bedroom: 3.0,
  master_bedroom: 3.0,
  kitchen: 2.6,
  toilet: 1.5,
  wc_only: 1.5,
  bathroom_master: 1.8,
};
const MIN_ROOM_SIDE_DEFAULT = 2.0;

function getMinSide(type: string): number {
  return MIN_ROOM_SIDE[type] ?? MIN_ROOM_SIDE_DEFAULT;
}

// ── Shared wall detection ─────────────────────────────────────────────────────
interface SharedWall {
  orientation: "vertical" | "horizontal";
  wallPos: number;
  roomA: RoomData;
  roomB: RoomData;
  segStart: number;
  segEnd: number;
}

const WALL_TOL = 0.01;

function detectSharedWalls(rooms: RoomData[]): SharedWall[] {
  const walls: SharedWall[] = [];
  for (let i = 0; i < rooms.length; i++) {
    for (let j = i + 1; j < rooms.length; j++) {
      const a = rooms[i];
      const b = rooms[j];
      const aRight = a.x + a.width;
      const bRight = b.x + b.width;
      if (Math.abs(aRight - b.x) < WALL_TOL) {
        const segStart = Math.max(a.y, b.y);
        const segEnd = Math.min(a.y + a.depth, b.y + b.depth);
        if (segEnd > segStart + WALL_TOL)
          walls.push({
            orientation: "vertical",
            wallPos: aRight,
            roomA: a,
            roomB: b,
            segStart,
            segEnd,
          });
      } else if (Math.abs(bRight - a.x) < WALL_TOL) {
        const segStart = Math.max(a.y, b.y);
        const segEnd = Math.min(a.y + a.depth, b.y + b.depth);
        if (segEnd > segStart + WALL_TOL)
          walls.push({
            orientation: "vertical",
            wallPos: bRight,
            roomA: b,
            roomB: a,
            segStart,
            segEnd,
          });
      }
      const aTop = a.y + a.depth;
      const bTop = b.y + b.depth;
      if (Math.abs(aTop - b.y) < WALL_TOL) {
        const segStart = Math.max(a.x, b.x);
        const segEnd = Math.min(a.x + a.width, b.x + b.width);
        if (segEnd > segStart + WALL_TOL)
          walls.push({
            orientation: "horizontal",
            wallPos: aTop,
            roomA: a,
            roomB: b,
            segStart,
            segEnd,
          });
      } else if (Math.abs(bTop - a.y) < WALL_TOL) {
        const segStart = Math.max(a.x, b.x);
        const segEnd = Math.min(a.x + a.width, b.x + b.width);
        if (segEnd > segStart + WALL_TOL)
          walls.push({
            orientation: "horizontal",
            wallPos: bTop,
            roomA: b,
            roomB: a,
            segStart,
            segEnd,
          });
      }
    }
  }
  return walls;
}

// ── L-shape polygon point helper ─────────────────────────────────────────────
function computeLShapePoints(
  plotWidth: number,
  plotLength: number,
  cutoutCorner: string,
  cutoutWidth: number,
  cutoutHeight: number,
  px: (x: number) => number,
  py: (y: number) => number
): string {
  const W = plotWidth;
  const H = plotLength;
  const cw = cutoutWidth;
  const ch = cutoutHeight;
  let vertices: [number, number][];
  if (cutoutCorner === "NE") {
    vertices = [
      [0, 0],
      [W, 0],
      [W, H - ch],
      [W - cw, H - ch],
      [W - cw, H],
      [0, H],
    ];
  } else if (cutoutCorner === "NW") {
    vertices = [
      [0, 0],
      [W, 0],
      [W, H],
      [cw, H],
      [cw, H - ch],
      [0, H - ch],
    ];
  } else if (cutoutCorner === "SE") {
    vertices = [
      [0, 0],
      [W - cw, 0],
      [W - cw, ch],
      [W, ch],
      [W, H],
      [0, H],
    ];
  } else {
    vertices = [
      [cw, 0],
      [W, 0],
      [W, H],
      [0, H],
      [0, ch],
      [cw, ch],
    ];
  }
  return vertices.map(([x, y]) => `${px(x)},${py(y)}`).join(" ");
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
  plotCorners?: [number, number][];
  showVastuZones?: boolean;
  showFurniture?: boolean;
  showElectrical?: boolean;
  showPlumbing?: boolean;
  annotationMode?: boolean;
  annotations?: Annotation[];
  onAnnotationClick?: (roomId: string, roomName: string, x: number, y: number) => void;
  locale?: Locale;
  cutoutCorner?: string;
  cutoutWidth?: number;
  cutoutHeight?: number;
  // ── Edit mode props (all optional — backward compatible) ──────────────────
  editMode?: boolean;
  onRoomsChange?: (rooms: RoomData[]) => void;
  complianceIssues?: Record<string, string[]>;
}

// ── Vastu zone colors (3×3 grid) ─────────────────────────────────────────────
// Ordered: row 0=rear (N-ish), row 1=middle, row 2=front (S-ish)
// col 0=left, col 1=center, col 2=right
// Colors follow classical Vastu auspiciousness:
//   NE(green/sacred), N(cyan/wealth), NW(slate), W(slate), C(amber/Brahma), E(blue), SE(orange/fire), S(slate), SW(red/bad)
const VASTU_ZONE_COLORS: Record<string, { fill: string; label: string[] }> = {
  NE: { fill: "rgba(34,197,94,0.22)", label: ["NE", "Ishanya"] },
  N: { fill: "rgba(6,182,212,0.18)", label: ["N", "Kubera"] },
  NW: { fill: "rgba(148,163,184,0.18)", label: ["NW", "Vayu"] },
  W: { fill: "rgba(148,163,184,0.18)", label: ["W", "Varuna"] },
  C: { fill: "rgba(251,191,36,0.20)", label: ["C", "Brahma"] },
  E: { fill: "rgba(59,130,246,0.18)", label: ["E", "Purva"] },
  SE: { fill: "rgba(249,115,22,0.20)", label: ["SE", "Agni"] },
  S: { fill: "rgba(148,163,184,0.18)", label: ["S", "Yama"] },
  SW: { fill: "rgba(239,68,68,0.22)", label: ["SW", "Nairutya"] },
};

// Zone grid for road facing South (default):
// row 0=rear/north, row 2=front/south  |  col 0=west, col 2=east
const VASTU_GRID_ROAD_S = [
  ["NW", "N", "NE"],
  ["W", "C", "E"],
  ["SW", "S", "SE"],
];
const VASTU_GRID_ROAD_N = [
  ["SE", "S", "SW"],
  ["E", "C", "W"],
  ["NE", "N", "NW"],
];
const VASTU_GRID_ROAD_E = [
  ["NE", "E", "SE"],
  ["N", "C", "S"],
  ["NW", "W", "SW"],
];
const VASTU_GRID_ROAD_W = [
  ["SW", "W", "NW"],
  ["S", "C", "N"],
  ["SE", "E", "NE"],
];
const VASTU_GRIDS: Record<string, string[][]> = {
  S: VASTU_GRID_ROAD_S,
  N: VASTU_GRID_ROAD_N,
  E: VASTU_GRID_ROAD_E,
  W: VASTU_GRID_ROAD_W,
};

export function FloorPlanSVG({
  floorPlan,
  plotWidth,
  plotLength,
  roadSide = "S",
  className,
  plotShape,
  plotFrontWidth,
  plotRearWidth,
  plotCorners,
  showVastuZones = false,
  showFurniture = false,
  showElectrical = false,
  showPlumbing = false,
  annotationMode = false,
  annotations = [],
  onAnnotationClick,
  locale = "en",
  cutoutCorner = "NE",
  cutoutWidth = 0,
  cutoutHeight = 0,
  editMode = false,
  onRoomsChange,
  complianceIssues = {},
}: FloorPlanSVGProps) {
  const northRotation = NORTH_ROTATION[roadSide] ?? 0;

  // ── Edit mode drag state ────────────────────────────────────────────────────
  interface DragState {
    wall: SharedWall;
    startSvgPos: number; // SVG px coordinate where drag started
    startWallPos: number; // metres position of wall when drag started
  }
  const dragRef = useRef<DragState | null>(null);
  const [editRooms, setEditRooms] = useState<RoomData[] | null>(null);
  const [hoveredWallKey, setHoveredWallKey] = useState<string | null>(null);
  const [dragTooltip, setDragTooltip] = useState<{
    svgX: number;
    svgY: number;
    widthA: number;
    depthA: number;
    widthB: number;
    depthB: number;
  } | null>(null);

  // The rooms to render — use editRooms if in edit mode and user has dragged, else floorPlan.rooms
  const displayRooms: RoomData[] = editMode && editRooms !== null ? editRooms : floorPlan.rooms;

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

  const rooms = displayRooms;

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

  // Build annotation lookup by room_id for quick access
  const annotationMap = new Map(annotations.map((a) => [a.room_id, a]));

  // ── Edit mode: shared wall list ─────────────────────────────────────────────
  const sharedWalls = editMode ? detectSharedWalls(rooms) : [];

  function wallKey(w: SharedWall): string {
    return `${w.orientation}-${w.wallPos.toFixed(3)}-${w.roomA.id}-${w.roomB.id}`;
  }

  function handleWallMouseDown(e: React.MouseEvent<SVGLineElement>, wall: SharedWall): void {
    if (!editMode) return;
    e.preventDefault();
    e.stopPropagation();
    const startPos = wall.orientation === "vertical" ? e.clientX : e.clientY;
    dragRef.current = {
      wall,
      startSvgPos: startPos,
      startWallPos: wall.wallPos,
    };
  }

  function handleSVGMouseMove(e: React.MouseEvent<SVGSVGElement>): void {
    if (!editMode || !dragRef.current) return;
    const drag = dragRef.current;

    const currentPos = drag.wall.orientation === "vertical" ? e.clientX : e.clientY;
    const svgEl = e.currentTarget;
    const rect = svgEl.getBoundingClientRect();
    const svgScale = VP_W / rect.width; // screen px → SVG px

    const deltaSvgPx = (currentPos - drag.startSvgPos) * svgScale;
    // vertical wall: positive delta = wall moves right (x increases)
    // horizontal wall: positive delta = wall moves down in screen (y increases in SVG) = y decreases in metres
    const deltaM = drag.wall.orientation === "vertical" ? deltaSvgPx / scale : -deltaSvgPx / scale;

    const newWallPos = drag.startWallPos + deltaM;

    // Compute current rooms (copy of latest editRooms or original)
    const baseRooms: RoomData[] = editRooms !== null ? editRooms : floorPlan.rooms;

    // Apply constraint: neither adjacent room shrinks below its minimum side
    const { roomA, roomB, orientation } = drag.wall;
    const rA = baseRooms.find((r) => r.id === roomA.id);
    const rB = baseRooms.find((r) => r.id === roomB.id);
    if (!rA || !rB) return;

    let clampedPos = newWallPos;
    if (orientation === "vertical") {
      // roomA is left (x + width = wall), roomB is right (x = wall)
      const minWallForA = rA.x + getMinSide(rA.type);
      const maxWallForB = rB.x + rB.width - getMinSide(rB.type);
      clampedPos = Math.max(minWallForA, Math.min(maxWallForB, clampedPos));
    } else {
      // roomA is below (y + depth = wall), roomB is above (y = wall)
      const minWallForA = rA.y + getMinSide(rA.type);
      const maxWallForB = rB.y + rB.depth - getMinSide(rB.type);
      clampedPos = Math.max(minWallForA, Math.min(maxWallForB, clampedPos));
    }

    const updatedRooms: RoomData[] = baseRooms.map((r) => {
      if (orientation === "vertical") {
        if (r.id === rA.id) {
          const newWidth = clampedPos - r.x;
          return { ...r, width: newWidth, area: parseFloat((newWidth * r.depth).toFixed(2)) };
        }
        if (r.id === rB.id) {
          const newX = clampedPos;
          const newWidth = rB.x + rB.width - clampedPos;
          return {
            ...r,
            x: newX,
            width: newWidth,
            area: parseFloat((newWidth * r.depth).toFixed(2)),
          };
        }
      } else {
        if (r.id === rA.id) {
          const newDepth = clampedPos - r.y;
          return { ...r, depth: newDepth, area: parseFloat((r.width * newDepth).toFixed(2)) };
        }
        if (r.id === rB.id) {
          const newY = clampedPos;
          const newDepth = rB.y + rB.depth - clampedPos;
          return {
            ...r,
            y: newY,
            depth: newDepth,
            area: parseFloat((r.width * newDepth).toFixed(2)),
          };
        }
      }
      return r;
    });

    setEditRooms(updatedRooms);

    // Show drag tooltip
    const updatedA = updatedRooms.find((r) => r.id === rA.id);
    const updatedB = updatedRooms.find((r) => r.id === rB.id);
    if (updatedA && updatedB) {
      const tooltipSvgX = orientation === "vertical" ? px(clampedPos) : px(rA.x + rA.width / 2);
      const tooltipSvgY =
        orientation === "vertical"
          ? py(drag.wall.segStart + (drag.wall.segEnd - drag.wall.segStart) / 2)
          : py(clampedPos);
      setDragTooltip({
        svgX: tooltipSvgX,
        svgY: tooltipSvgY,
        widthA: updatedA.width,
        depthA: updatedA.depth,
        widthB: updatedB.width,
        depthB: updatedB.depth,
      });
    }
  }

  function handleSVGMouseUp(): void {
    if (!editMode || !dragRef.current) return;
    dragRef.current = null;
    setDragTooltip(null);
    if (editRooms !== null && onRoomsChange) {
      onRoomsChange(editRooms);
    }
  }

  function handleSVGMouseLeave(): void {
    if (dragRef.current) {
      handleSVGMouseUp();
    }
  }

  return (
    <TooltipProvider>
      <svg
        viewBox={`0 0 ${VP_W} ${VP_H}`}
        className={["floor-plan-svg", className].filter(Boolean).join(" ")}
        style={{ width: "100%", height: "auto", cursor: annotationMode ? "crosshair" : undefined }}
        aria-label="Floor plan diagram"
        onMouseMove={editMode ? handleSVGMouseMove : undefined}
        onMouseUp={editMode ? handleSVGMouseUp : undefined}
        onMouseLeave={editMode ? handleSVGMouseLeave : undefined}
      >
        {/* Background */}
        <rect width={VP_W} height={VP_H} fill="#F8FAFC" rx={6} className="svg-bg" />

        {/* Road strip */}
        <rect
          x={originX}
          y={originY + drawH + 2}
          width={drawW}
          height={ROAD_H}
          fill="#CBD5E1"
          rx={2}
          className="svg-road"
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
        {plotShape === "quadrilateral" && plotCorners && plotCorners.length === 4 ? (
          <polygon
            points={plotCorners.map(([cx, cy]) => `${px(cx)},${py(cy)}`).join(" ")}
            fill="white"
            stroke="#CBD5E1"
            strokeWidth={1}
            strokeDasharray="5 3"
            className="svg-plot"
          />
        ) : plotShape === "l_shaped" && cutoutWidth > 0 && cutoutHeight > 0 ? (
          <polygon
            points={computeLShapePoints(
              plotWidth,
              plotLength,
              cutoutCorner,
              cutoutWidth,
              cutoutHeight,
              px,
              py
            )}
            fill="white"
            stroke="#CBD5E1"
            strokeWidth={1}
            strokeDasharray="5 3"
            className="svg-plot"
          />
        ) : plotShape === "trapezoid" && plotFrontWidth && plotRearWidth ? (
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
                className="svg-plot"
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
            className="svg-plot"
          />
        )}

        {/* ── Vastu zone overlay (3×3 grid) ─────────────────────────────── */}
        {showVastuZones &&
          (() => {
            const grid = VASTU_GRIDS[roadSide?.toUpperCase() ?? "S"] ?? VASTU_GRID_ROAD_S;
            const zW = drawW / 3;
            const zH = drawH / 3;
            const cells: React.ReactNode[] = [];
            for (let row = 0; row < 3; row++) {
              for (let col = 0; col < 3; col++) {
                const zoneName = grid[row][col];
                const zoneInfo = VASTU_ZONE_COLORS[zoneName] ?? {
                  fill: "rgba(148,163,184,0.15)",
                  label: zoneName,
                };
                const zx = originX + col * zW;
                // row 0 = rear (top of SVG), row 2 = front (bottom) — SVG y increases downward
                const zy = originY + row * zH;
                const lines = zoneInfo.label;
                cells.push(
                  <g key={`vz-${row}-${col}`}>
                    <rect
                      x={zx}
                      y={zy}
                      width={zW}
                      height={zH}
                      fill={zoneInfo.fill}
                      stroke="rgba(148,163,184,0.3)"
                      strokeWidth={0.5}
                    />
                    {lines.map((line, li) => (
                      <text
                        key={`${zoneName}-${line}`}
                        x={zx + zW / 2}
                        y={zy + zH / 2 + (li - (lines.length - 1) / 2) * 10}
                        textAnchor="middle"
                        dominantBaseline="middle"
                        fontSize={li === 0 ? 9 : 7}
                        fontFamily="sans-serif"
                        fontWeight={li === 0 ? "700" : "400"}
                        fill="rgba(30,41,59,0.55)"
                      >
                        {line}
                      </text>
                    ))}
                  </g>
                );
              }
            }
            return <g opacity={1}>{cells}</g>;
          })()}

        {/* ── Room fills ─────────────────────────────────────────────────── */}
        {rooms.map((room) => {
          const rx = px(room.x);
          const ry = py(room.y + room.depth);
          const rw = room.width * scale;
          const rh = room.depth * scale;
          const roomCx = px(room.x + room.width / 2);
          const roomCy = py(room.y + room.depth / 2);
          const hasIssue =
            editMode && complianceIssues[room.id] && complianceIssues[room.id].length > 0;

          if (annotationMode && onAnnotationClick) {
            const handleAnnotClick = () => onAnnotationClick(room.id, room.name, roomCx, roomCy);
            return (
              <g
                key={room.id}
                tabIndex={0}
                style={{ cursor: "pointer", outline: "none" }}
                onClick={handleAnnotClick}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") handleAnnotClick();
                }}
                aria-label={String(room.name)}
              >
                <rect
                  x={rx}
                  y={ry}
                  width={rw}
                  height={rh}
                  fill={color(room.type).fill}
                  stroke={color(room.type).stroke}
                  strokeWidth={1.5}
                  strokeDasharray="3 2"
                />
              </g>
            );
          }
          if (hasIssue) {
            return (
              <g key={room.id}>
                <rect x={rx} y={ry} width={rw} height={rh} fill="rgba(239,68,68,0.1)" />
                <rect
                  x={rx}
                  y={ry}
                  width={rw}
                  height={rh}
                  fill="none"
                  stroke="#ef4444"
                  strokeWidth={1.5}
                  strokeDasharray="4 2"
                />
              </g>
            );
          }
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

        {/* ── Staircase treads ──────────────────────────────────────────── */}
        {rooms
          .filter((r) => r.type === "staircase")
          .map((room) => (
            <StaircaseSymbol key={`stair-${room.id}`} room={room} px={px} py={py} scale={scale} />
          ))}

        {/* ── Room furniture ────────────────────────────────────────────── */}
        {rooms
          .filter((r) => r.width * scale >= 30 && r.depth * scale >= 30)
          .map((room) => (
            <RoomFurniture key={`furn-${room.id}`} room={room} px={px} py={py} scale={scale} />
          ))}

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
          <RoomLabel
            key={`lbl-${room.id}`}
            room={room}
            px={px}
            py={py}
            scale={scale}
            locale={locale}
          />
        ))}

        {/* ── Edit mode: compliance violation badges ─────────────────────── */}
        {editMode &&
          rooms.map((room) => {
            const issues = complianceIssues[room.id];
            if (!issues || issues.length === 0) return null;
            const cx = px(room.x + room.width / 2);
            // Place badge below room label — shift down by ~24px from centre
            const cy = py(room.y + room.depth / 2) + 24;
            const label = issues[0].length > 22 ? `${issues[0].slice(0, 20)}…` : issues[0];
            const badgeW = label.length * 4.8 + 12;
            return (
              <g key={`ci-${room.id}`}>
                <rect
                  x={cx - badgeW / 2}
                  y={cy - 7}
                  width={badgeW}
                  height={13}
                  rx={3}
                  fill="#ef4444"
                  fillOpacity={0.92}
                />
                <text
                  x={cx}
                  y={cy + 2}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fontSize={7}
                  fontFamily="sans-serif"
                  fill="white"
                  fontWeight="600"
                >
                  {label}
                </text>
              </g>
            );
          })}

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

        {/* ── Furniture overlay (presentation mode) ─────────────────────── */}
        {showFurniture && (
          <FurnitureOverlay
            rooms={rooms}
            scale={scale}
            offsetX={originX}
            offsetY={originY}
            plotHeightPx={drawH}
          />
        )}

        {/* ── Electrical overlay ─────────────────────────────────────────── */}
        {showElectrical && (
          <ElectricalOverlay
            rooms={rooms}
            scale={scale}
            offsetX={originX}
            offsetY={originY}
            plotHeightPx={drawH}
          />
        )}

        {/* ── Plumbing overlay ───────────────────────────────────────────── */}
        {showPlumbing && (
          <PlumbingOverlay
            rooms={rooms}
            scale={scale}
            offsetX={originX}
            offsetY={originY}
            plotHeightPx={drawH}
          />
        )}

        {/* ── Annotation sticky-note icons ───────────────────────────────── */}
        {annotations.length > 0 &&
          rooms.map((room) => {
            const ann = annotationMap.get(room.id);
            if (!ann || !ann.note) return null;
            const noteX = px(room.x + room.width / 2) - 10;
            const noteY = py(room.y + room.depth / 2) - 10;
            return (
              <Tooltip key={`ann-${room.id}`}>
                <TooltipTrigger asChild>
                  <g style={{ cursor: "pointer" }}>
                    {/* Sticky note yellow rect */}
                    <rect
                      x={noteX}
                      y={noteY}
                      width={20}
                      height={20}
                      rx={2}
                      fill="#FEF08A"
                      stroke="#CA8A04"
                      strokeWidth={0.8}
                    />
                    {/* Fold corner */}
                    <path
                      d={`M ${noteX + 14} ${noteY} L ${noteX + 20} ${noteY + 6} L ${noteX + 14} ${noteY + 6} Z`}
                      fill="#FDE047"
                      stroke="#CA8A04"
                      strokeWidth={0.5}
                    />
                    {/* N text */}
                    <text
                      x={noteX + 7}
                      y={noteY + 14}
                      fontSize={8}
                      fontWeight="700"
                      fill="#713F12"
                      fontFamily="sans-serif"
                    >
                      N
                    </text>
                  </g>
                </TooltipTrigger>
                <TooltipContent side="top" className="max-w-xs">
                  <p className="font-semibold text-xs mb-0.5">{ann.room_name}</p>
                  <p className="text-xs">{ann.note}</p>
                </TooltipContent>
              </Tooltip>
            );
          })}

        {/* ── Edit mode: draggable shared wall handles ───────────────────── */}
        {editMode &&
          sharedWalls.map((wall) => {
            const key = wallKey(wall);
            const isHovered = hoveredWallKey === key;
            const isDragging = dragRef.current !== null && wallKey(dragRef.current.wall) === key;
            const active = isHovered || isDragging;

            if (wall.orientation === "vertical") {
              const svgX = px(wall.wallPos);
              const svgY1 = py(wall.segEnd);
              const svgY2 = py(wall.segStart);
              return (
                <line
                  key={key}
                  x1={svgX}
                  y1={svgY1}
                  x2={svgX}
                  y2={svgY2}
                  stroke={active ? "#1d4ed8" : "#3b82f6"}
                  strokeWidth={active ? 3 : 2}
                  strokeOpacity={active ? 1 : 0.7}
                  style={{ cursor: "ew-resize" }}
                  onMouseEnter={() => setHoveredWallKey(key)}
                  onMouseLeave={() => setHoveredWallKey(null)}
                  onMouseDown={(e) => handleWallMouseDown(e, wall)}
                />
              );
            } else {
              const svgY = py(wall.wallPos);
              const svgX1 = px(wall.segStart);
              const svgX2 = px(wall.segEnd);
              return (
                <line
                  key={key}
                  x1={svgX1}
                  y1={svgY}
                  x2={svgX2}
                  y2={svgY}
                  stroke={active ? "#1d4ed8" : "#3b82f6"}
                  strokeWidth={active ? 3 : 2}
                  strokeOpacity={active ? 1 : 0.7}
                  style={{ cursor: "ns-resize" }}
                  onMouseEnter={() => setHoveredWallKey(key)}
                  onMouseLeave={() => setHoveredWallKey(null)}
                  onMouseDown={(e) => handleWallMouseDown(e, wall)}
                />
              );
            }
          })}

        {/* ── Edit mode: drag tooltip ────────────────────────────────────── */}
        {editMode &&
          dragTooltip &&
          (() => {
            const tx = dragTooltip.svgX + 6;
            const ty = dragTooltip.svgY - 36;
            const areaA = (dragTooltip.widthA * dragTooltip.depthA).toFixed(1);
            const areaB = (dragTooltip.widthB * dragTooltip.depthB).toFixed(1);
            const line1 = `${dragTooltip.widthA.toFixed(1)}×${dragTooltip.depthA.toFixed(1)}=${areaA}㎡`;
            const line2 = `${dragTooltip.widthB.toFixed(1)}×${dragTooltip.depthB.toFixed(1)}=${areaB}㎡`;
            const boxW = Math.max(line1.length, line2.length) * 5.2 + 10;
            return (
              <g>
                <rect
                  x={tx - 4}
                  y={ty - 10}
                  width={boxW}
                  height={32}
                  rx={3}
                  fill="#1e293b"
                  fillOpacity={0.88}
                />
                <text x={tx} y={ty + 4} fontSize={9} fill="white" fontFamily="monospace">
                  {line1}
                </text>
                <text x={tx} y={ty + 16} fontSize={9} fill="#93c5fd" fontFamily="monospace">
                  {line2}
                </text>
              </g>
            );
          })()}
      </svg>
    </TooltipProvider>
  );
}
