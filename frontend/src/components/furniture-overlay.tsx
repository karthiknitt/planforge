"use client";

import type { RoomData } from "@/lib/layout-types";

interface FurnitureOverlayProps {
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

const FURN_STROKE = "#94a3b8";
const FURN_FILL = "#f8fafc";
const FURN_OPACITY = 0.75;
const FURN_SW = 0.5;

// ── Label under furniture ──────────────────────────────────────────────────────
function FurnLabel({ x, y, text }: { x: number; y: number; text: string }) {
  return (
    <text
      x={x}
      y={y}
      textAnchor="middle"
      fontSize={5}
      fontFamily="sans-serif"
      fill="#64748b"
      stroke="none"
    >
      {text}
    </text>
  );
}

// ── Double / King bed ──────────────────────────────────────────────────────────
function BedSymbol({
  room,
  px,
  py,
  scale,
  isKing,
}: {
  room: RoomData;
  px: (v: number) => number;
  py: (v: number) => number;
  scale: number;
  isKing: boolean;
}) {
  const bedW = isKing ? 1.8 : 1.5;
  const bedD = isKing ? 2.0 : 1.9;
  const margin = 0.15;

  if (room.width < bedW + 2 * margin || room.depth < bedD + margin) return null;

  // Place bed centred horizontally, at the "far" wall (top of room in metre space = high y)
  const bx = room.x + (room.width - bedW) / 2;
  const by = room.y + room.depth - margin - bedD;

  const rx = px(bx);
  const ry = py(by + bedD); // top-left in SVG (ry is smaller for higher y in metre space)
  const rw = bedW * scale;
  const rh = bedD * scale;
  const headH = 0.12 * scale;
  const pillowR = 0.22 * scale;

  return (
    <g stroke={FURN_STROKE} strokeWidth={FURN_SW} fill={FURN_FILL} opacity={FURN_OPACITY}>
      {/* Bed frame */}
      <rect x={rx} y={ry} width={rw} height={rh} />
      {/* Headboard */}
      <rect x={rx} y={ry} width={rw} height={headH} fill="#cbd5e1" />
      {/* Left pillow */}
      <ellipse
        cx={rx + rw * 0.28}
        cy={ry + headH + pillowR * 0.9}
        rx={pillowR}
        ry={pillowR * 0.55}
      />
      {/* Right pillow */}
      <ellipse
        cx={rx + rw * 0.72}
        cy={ry + headH + pillowR * 0.9}
        rx={pillowR}
        ry={pillowR * 0.55}
      />
      {/* Blanket fold line */}
      <line x1={rx} y1={ry + rh * 0.35} x2={rx + rw} y2={ry + rh * 0.35} />
      <FurnLabel x={rx + rw / 2} y={ry + rh + 6} text={isKing ? "King Bed" : "Dbl Bed"} />
    </g>
  );
}

// ── Wardrobe ───────────────────────────────────────────────────────────────────
function WardrobeSymbol({
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
  const wW = 0.9;
  const wD = 0.5;
  const margin = 0.1;

  if (room.width < wW + 2 * margin || room.depth < wD + margin) return null;

  // Place wardrobe on the adjacent (left) wall of the room — left side, near top wall
  const wx = room.x + margin;
  const wy = room.y + room.depth - margin - wD;

  const rx = px(wx);
  const ry = py(wy + wD);
  const rw = wW * scale;
  const rh = wD * scale;
  const mid = rx + rw / 2;

  return (
    <g stroke={FURN_STROKE} strokeWidth={FURN_SW} fill={FURN_FILL} opacity={FURN_OPACITY}>
      <rect x={rx} y={ry} width={rw} height={rh} />
      {/* Sliding door divider */}
      <line x1={mid} y1={ry} x2={mid} y2={ry + rh} />
      {/* Door handle left */}
      <line x1={mid - rw * 0.12} y1={ry + rh * 0.5} x2={mid - rw * 0.02} y2={ry + rh * 0.5} />
      {/* Door handle right */}
      <line x1={mid + rw * 0.02} y1={ry + rh * 0.5} x2={mid + rw * 0.12} y2={ry + rh * 0.5} />
      <FurnLabel x={rx + rw / 2} y={ry + rh + 6} text="Wardrobe" />
    </g>
  );
}

// ── 3-seat sofa ────────────────────────────────────────────────────────────────
function SofaSymbol({
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
  const sofaW = Math.min(2.1, room.width - 0.3);
  const sofaD = 0.9;
  const margin = 0.15;

  if (sofaW < 1.2 || room.depth < sofaD + margin) return null;

  // Place sofa along bottom wall (low y in metre space = front of room)
  const sx = room.x + (room.width - sofaW) / 2;
  const sy = room.y + margin;

  const rx = px(sx);
  const ry = py(sy + sofaD);
  const rw = sofaW * scale;
  const rh = sofaD * scale;

  const armW = 0.25 * scale;
  const cushionW = (rw - 2 * armW) / 3;
  const cushionH = rh * 0.65;
  const cushionY = ry + rh - cushionH;

  return (
    <g stroke={FURN_STROKE} strokeWidth={FURN_SW} fill={FURN_FILL} opacity={FURN_OPACITY}>
      {/* Sofa body */}
      <rect x={rx} y={ry} width={rw} height={rh} />
      {/* Left armrest */}
      <rect x={rx} y={ry} width={armW} height={rh} fill="#e2e8f0" />
      {/* Right armrest */}
      <rect x={rx + rw - armW} y={ry} width={armW} height={rh} fill="#e2e8f0" />
      {/* 3 cushion arcs */}
      {[0, 1, 2].map((i) => {
        const cxVal = rx + armW + i * cushionW + cushionW / 2;
        const cyVal = cushionY + cushionH / 2;
        const cr = cushionW * 0.38;
        return (
          <ellipse
            key={i}
            cx={cxVal}
            cy={cyVal}
            rx={cr}
            ry={cushionH * 0.42}
            fill="#e2e8f0"
            stroke={FURN_STROKE}
            strokeWidth={FURN_SW}
          />
        );
      })}
      <FurnLabel x={rx + rw / 2} y={ry - 3} text="3-Seat Sofa" />
    </g>
  );
}

// ── Coffee table ───────────────────────────────────────────────────────────────
function CoffeeTableSymbol({
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
  const tW = Math.min(0.9, room.width * 0.5);
  const tD = 0.5;
  const sofaD = 0.9;
  const margin = 0.15;

  if (tW < 0.5 || room.depth < sofaD + tD + 0.4 + margin) return null;

  // Place 0.4 m in front of sofa (sofa is at room.y + margin)
  const tx = room.x + (room.width - tW) / 2;
  const ty = room.y + margin + sofaD + 0.4;

  const rx = px(tx);
  const ry = py(ty + tD);
  const rw = tW * scale;
  const rh = tD * scale;

  return (
    <g
      stroke={FURN_STROKE}
      strokeWidth={FURN_SW}
      fill={FURN_FILL}
      opacity={FURN_OPACITY}
      strokeDasharray="3 2"
    >
      <rect x={rx} y={ry} width={rw} height={rh} />
      <FurnLabel x={rx + rw / 2} y={ry + rh + 6} text="Coffee Tbl" />
    </g>
  );
}

// ── Dining table 4-seat ────────────────────────────────────────────────────────
function DiningTableSymbol({
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
  const margin = 0.4;
  const tW = Math.min(1.2, room.width - 2 * margin);
  const tD = Math.min(0.8, room.depth - 2 * margin);

  if (tW < 0.7 || tD < 0.4) return null;

  const tx = room.x + (room.width - tW) / 2;
  const ty = room.y + (room.depth - tD) / 2;

  const rx = px(tx);
  const ry = py(ty + tD);
  const rw = tW * scale;
  const rh = tD * scale;
  const chairW = 0.4 * scale;
  const chairH = 0.35 * scale;
  const gap = 3;

  return (
    <g stroke={FURN_STROKE} strokeWidth={FURN_SW} fill={FURN_FILL} opacity={FURN_OPACITY}>
      {/* Table */}
      <rect x={rx} y={ry} width={rw} height={rh} />
      {/* Top chairs (2) */}
      <rect x={rx + rw * 0.15} y={ry - gap - chairH} width={chairW} height={chairH} />
      <rect x={rx + rw * 0.55} y={ry - gap - chairH} width={chairW} height={chairH} />
      {/* Bottom chairs (2) */}
      <rect x={rx + rw * 0.15} y={ry + rh + gap} width={chairW} height={chairH} />
      <rect x={rx + rw * 0.55} y={ry + rh + gap} width={chairW} height={chairH} />
      <FurnLabel x={rx + rw / 2} y={ry + rh + chairH + gap + 7} text="Dining Table" />
    </g>
  );
}

// ── L-kitchen counter with sink ────────────────────────────────────────────────
function KitchenCounterSymbol({
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
  const cDepth = 0.6;
  const margin = 0.05;

  if (room.width < 1.5 || room.depth < 1.5) return null;

  const rx = room.x;
  const ry = room.y;
  const rw = room.width;
  const rd = room.depth;

  // Bottom counter (along low-y wall in metre space)
  const botX = rx + margin;
  const botY = ry + margin;
  const botW = rw - 2 * margin;
  const botD = cDepth;

  // Left counter (along left wall, excluding bottom corner overlap)
  const leftX = rx + margin;
  const leftY = botY + cDepth;
  const leftD = rd - 2 * margin - cDepth;

  // Sink circle on bottom counter (near right end)
  const sinkCx = rx + rw - margin - 0.35;
  const sinkCy = botY + cDepth / 2;

  // Stove burners on bottom counter (left portion)
  const burnerY = botY + cDepth / 2;
  const burner1X = rx + margin + 0.25;
  const burner2X = rx + margin + 0.55;

  return (
    <g stroke={FURN_STROKE} strokeWidth={FURN_SW} fill={FURN_FILL} opacity={FURN_OPACITY}>
      {/* Bottom counter */}
      <rect
        x={px(botX)}
        y={py(botY + botD)}
        width={botW * scale}
        height={botD * scale}
        fill="#dcfce7"
      />
      {/* Left counter */}
      {leftD > 0.5 && (
        <rect
          x={px(leftX)}
          y={py(leftY + leftD)}
          width={cDepth * scale}
          height={leftD * scale}
          fill="#dcfce7"
        />
      )}
      {/* Sink */}
      <circle cx={px(sinkCx)} cy={py(sinkCy)} r={0.18 * scale} />
      <circle cx={px(sinkCx)} cy={py(sinkCy)} r={0.07 * scale} fill="#bae6fd" />
      {/* Stove burners */}
      <circle cx={px(burner1X)} cy={py(burnerY)} r={0.09 * scale} />
      <circle cx={px(burner2X)} cy={py(burnerY)} r={0.09 * scale} />
      <FurnLabel
        x={px(rx + rw / 2)}
        y={py(botY + botD) + botD * scale + 7}
        text="Kitchen Counter"
      />
    </g>
  );
}

// ── WC (toilet seat) ───────────────────────────────────────────────────────────
function WCSymbol({
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
  const margin = 0.08;
  if (room.width < 0.7 || room.depth < 0.7) return null;

  // Place WC in far corner (top-right in metre space: high x, high y)
  const wcW = 0.4;
  const wcD = 0.6;
  const wx = room.x + room.width - margin - wcW;
  const wy = room.y + room.depth - margin - wcD;

  const rx = px(wx);
  const ry = py(wy + wcD);
  const rw = wcW * scale;
  const rh = wcD * scale;
  const tankH = 0.14 * scale;

  return (
    <g stroke={FURN_STROKE} strokeWidth={FURN_SW} fill={FURN_FILL} opacity={FURN_OPACITY}>
      {/* Tank */}
      <rect x={rx} y={ry} width={rw} height={tankH} fill="#e0f2fe" />
      {/* Bowl ellipse */}
      <ellipse cx={rx + rw / 2} cy={ry + tankH + rh * 0.35} rx={rw * 0.42} ry={rh * 0.38} />
      {/* Seat outline */}
      <ellipse cx={rx + rw / 2} cy={ry + tankH + rh * 0.38} rx={rw * 0.48} ry={rh * 0.44} />
      <FurnLabel x={rx + rw / 2} y={ry + rh + 6} text="WC" />
    </g>
  );
}

// ── Washbasin ──────────────────────────────────────────────────────────────────
function WashbasinSymbol({
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
  const margin = 0.08;
  if (room.width < 0.8 || room.depth < 0.7) return null;

  // Place washbasin beside WC — near top-left corner (low x, high y)
  const bW = 0.5;
  const bD = 0.4;
  const bx = room.x + margin;
  const by = room.y + room.depth - margin - bD;

  const rx = px(bx);
  const ry = py(by + bD);
  const rw = bW * scale;
  const rh = bD * scale;

  return (
    <g stroke={FURN_STROKE} strokeWidth={FURN_SW} fill={FURN_FILL} opacity={FURN_OPACITY}>
      {/* Basin rect */}
      <rect x={rx} y={ry} width={rw} height={rh} />
      {/* Basin bowl circle */}
      <circle cx={rx + rw / 2} cy={ry + rh / 2} r={Math.min(rw, rh) * 0.35} />
      {/* Tap dot */}
      <circle cx={rx + rw / 2} cy={ry + rh * 0.12} r={2} fill="#94a3b8" />
      <FurnLabel x={rx + rw / 2} y={ry + rh + 6} text="Basin" />
    </g>
  );
}

// ── Car symbol ─────────────────────────────────────────────────────────────────
function CarSymbol({
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
  const carW = Math.min(2.4, room.width - 0.4);
  const carD = Math.min(4.8, room.depth - 0.4);
  const margin = 0.2;

  if (carW < 1.5 || carD < 2.0) return null;

  const cx = room.x + (room.width - carW) / 2;
  const cy = room.y + (room.depth - carD) / 2;

  const rx = px(cx);
  const ry = py(cy + carD);
  const rw = carW * scale;
  const rh = carD * scale;
  const rr = Math.min(rw, rh) * 0.06; // rounded corner radius

  // 4 wheels
  const wheelW = 0.3 * scale;
  const wheelH = 0.55 * scale;
  const wheelInsetX = margin * scale * 0.3;
  const wheelInsetY = rh * 0.12;

  return (
    <g stroke={FURN_STROKE} strokeWidth={FURN_SW} fill={FURN_FILL} opacity={FURN_OPACITY}>
      {/* Car body */}
      <rect x={rx} y={ry} width={rw} height={rh} rx={rr} ry={rr} />
      {/* Windscreen line */}
      <line x1={rx + rw * 0.12} y1={ry + rh * 0.22} x2={rx + rw * 0.88} y2={ry + rh * 0.22} />
      {/* Rear window line */}
      <line x1={rx + rw * 0.12} y1={ry + rh * 0.78} x2={rx + rw * 0.88} y2={ry + rh * 0.78} />
      {/* 4 wheels */}
      <rect
        x={rx - wheelW + wheelInsetX}
        y={ry + wheelInsetY}
        width={wheelW}
        height={wheelH}
        rx={2}
        ry={2}
        fill="#cbd5e1"
      />
      <rect
        x={rx + rw - wheelInsetX}
        y={ry + wheelInsetY}
        width={wheelW}
        height={wheelH}
        rx={2}
        ry={2}
        fill="#cbd5e1"
      />
      <rect
        x={rx - wheelW + wheelInsetX}
        y={ry + rh - wheelInsetY - wheelH}
        width={wheelW}
        height={wheelH}
        rx={2}
        ry={2}
        fill="#cbd5e1"
      />
      <rect
        x={rx + rw - wheelInsetX}
        y={ry + rh - wheelInsetY - wheelH}
        width={wheelW}
        height={wheelH}
        rx={2}
        ry={2}
        fill="#cbd5e1"
      />
      <FurnLabel x={rx + rw / 2} y={ry + rh + 6} text="Car" />
    </g>
  );
}

// ── Stair arrow ────────────────────────────────────────────────────────────────
function StairArrowSymbol({
  room,
  px,
  py,
}: {
  room: RoomData;
  px: (v: number) => number;
  py: (v: number) => number;
}) {
  // Diagonal arrow from bottom-left to top-right of the staircase room
  const x1 = px(room.x + 0.2);
  const y1 = py(room.y + 0.2);
  const x2 = px(room.x + room.width - 0.2);
  const y2 = py(room.y + room.depth - 0.2);

  const len = Math.hypot(x2 - x1, y2 - y1);
  if (len < 10) return null;

  const arrowSize = Math.min(8, len * 0.15);
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const ax1 = x2 - arrowSize * Math.cos(angle - 0.4);
  const ay1 = y2 - arrowSize * Math.sin(angle - 0.4);
  const ax2 = x2 - arrowSize * Math.cos(angle + 0.4);
  const ay2 = y2 - arrowSize * Math.sin(angle + 0.4);

  return (
    <g stroke={FURN_STROKE} strokeWidth={0.8} fill="none" opacity={FURN_OPACITY}>
      <line x1={x1} y1={y1} x2={x2} y2={y2} />
      <line x1={x2} y1={y2} x2={ax1} y2={ay1} />
      <line x1={x2} y1={y2} x2={ax2} y2={ay2} />
    </g>
  );
}

// ── Per-room furniture dispatcher ──────────────────────────────────────────────
function RoomFurnitureSymbols({
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
  switch (room.type) {
    case "bedroom":
    case "servant_quarter":
      return (
        <g>
          <BedSymbol room={room} px={px} py={py} scale={scale} isKing={false} />
          <WardrobeSymbol room={room} px={px} py={py} scale={scale} />
        </g>
      );
    case "master_bedroom":
      return (
        <g>
          <BedSymbol room={room} px={px} py={py} scale={scale} isKing={true} />
          <WardrobeSymbol room={room} px={px} py={py} scale={scale} />
        </g>
      );
    case "living":
      return (
        <g>
          <SofaSymbol room={room} px={px} py={py} scale={scale} />
          <CoffeeTableSymbol room={room} px={px} py={py} scale={scale} />
        </g>
      );
    case "dining":
      return <DiningTableSymbol room={room} px={px} py={py} scale={scale} />;
    case "kitchen":
      return <KitchenCounterSymbol room={room} px={px} py={py} scale={scale} />;
    case "toilet":
    case "bathroom":
    case "wc_only":
    case "bathroom_master":
      return (
        <g>
          <WCSymbol room={room} px={px} py={py} scale={scale} />
          <WashbasinSymbol room={room} px={px} py={py} scale={scale} />
        </g>
      );
    case "parking":
    case "parking_4w":
    case "garage":
      return <CarSymbol room={room} px={px} py={py} scale={scale} />;
    case "staircase":
      return <StairArrowSymbol room={room} px={px} py={py} />;
    default:
      return null;
  }
}

// ── Main exported component ────────────────────────────────────────────────────
export function FurnitureOverlay({
  rooms,
  scale,
  offsetX,
  offsetY,
  plotHeightPx,
}: FurnitureOverlayProps) {
  const { px, py } = mkPx(offsetX, offsetY, plotHeightPx, scale);

  return (
    <g className="furniture-overlay">
      {rooms
        .filter((r) => r.width * scale >= 28 && r.depth * scale >= 28)
        .map((room) => (
          <RoomFurnitureSymbols key={`fo-${room.id}`} room={room} px={px} py={py} scale={scale} />
        ))}
    </g>
  );
}
