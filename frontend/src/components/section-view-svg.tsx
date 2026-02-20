/**
 * 2D parametric section view for G+1 residential building.
 * Shows a vertical cut through the building: foundation → ground floor →
 * first floor slab → first floor → roof slab → parapet.
 *
 * All dimensions are in metres. Section is cut through the middle of the plot
 * (perpendicular to the road-facing facade).
 */

const VP_W = 620;
const VP_H = 480;
const PAD_X = 60; // left/right padding (for dimension labels)
const PAD_T = 24; // top padding
const PAD_B = 40; // bottom padding (for ground label + scale bar)

// ── Building parameters (Indian residential standard) ────────────────────────
const GF_H = 3.0; // ground floor clear height (m)
const FF_H = 3.0; // first floor clear height (m)
const SLAB_T = 0.15; // slab thickness (m)
const PARAPET_H = 1.0; // parapet height above roof slab (m)
const FOUND_D = 0.6; // foundation depth below GL (m)

// Total height from bottom of foundation to parapet top
const TOTAL_H = FOUND_D + GF_H + SLAB_T + FF_H + SLAB_T + PARAPET_H;

// Key elevation levels (from GL = 0)
const EL_FOUND_BOT = -FOUND_D;
const EL_GL = 0;
const EL_GF_TOP = GF_H;
const EL_FF_SLAB_TOP = GF_H + SLAB_T;
const EL_FF_TOP = GF_H + SLAB_T + FF_H;
const EL_ROOF_TOP = GF_H + SLAB_T + FF_H + SLAB_T;
const EL_PARAPET_TOP = EL_ROOF_TOP + PARAPET_H;

const EWT = 0.23; // external wall thickness (m)

function fmt(v: number): string {
  return v.toFixed(2);
}

interface SectionViewSVGProps {
  buildingWidth: number; // metres (plot width after setbacks)
  className?: string;
}

export function SectionViewSVG({ buildingWidth, className }: SectionViewSVGProps) {
  const drawW = VP_W - 2 * PAD_X;
  const drawH = VP_H - PAD_T - PAD_B;

  const scaleX = drawW / buildingWidth;
  const scaleY = drawH / TOTAL_H;
  const scale = Math.min(scaleX, scaleY);

  const bPx = buildingWidth * scale;
  const totalHPx = TOTAL_H * scale;

  const ox = PAD_X + (drawW - bPx) / 2;
  // oy = SVG y of the GL (ground level line)
  const oy = PAD_T + FOUND_D * scale + (drawH - totalHPx) / 2;

  // Convert elevation (m, 0=GL, positive = up) to SVG y coordinate
  const sy = (elev: number) => oy - elev * scale;

  // Convert width (m) to pixel
  const sw = (w: number) => w * scale;

  const wallX_L = ox;
  const wallX_R = ox + bPx;

  // Stair profile: simplified stepped shape on left side
  // ~17 risers × 175mm riser, 250mm tread
  const nSteps = 17;
  const riserH = 0.175; // m
  const treadW = 0.25; // m
  const stairTotH = nSteps * riserH;
  const stairX0 = wallX_L + sw(EWT);
  const stairY0 = sy(stairTotH); // top of stair at this elevation

  function buildStairPath(): string {
    let d = `M ${stairX0} ${sy(0)}`;
    for (let i = 0; i < nSteps; i++) {
      const rH = sw(riserH);
      const rW = sw(treadW);
      d += ` v ${-rH} h ${rW}`;
    }
    d += ` v ${sy(0) - sy(stairTotH)} H ${stairX0} Z`;
    return d;
  }

  const dimColor = "#94A3B8";
  const wallColor = "#1E293B";
  const slabColor = "#475569";
  const foundColor = "#92400E";
  const groundColor = "#D97706";
  const textColor = "#334155";

  return (
    <svg
      viewBox={`0 0 ${VP_W} ${VP_H}`}
      className={["section-view-svg", className].filter(Boolean).join(" ")}
      style={{ width: "100%", height: "auto" }}
      aria-label="Building section view"
    >
      {/* Background */}
      <rect width={VP_W} height={VP_H} fill="#F8FAFC" rx={6} className="svg-bg" />

      {/* ── Ground hatch below GL ─────────────────────────────────── */}
      <rect
        x={ox - 10}
        y={sy(EL_GL)}
        width={bPx + 20}
        height={sw(FOUND_D) + 10}
        fill="#FEF3C7"
        opacity={0.5}
      />

      {/* ── Foundation footings (schematic) ──────────────────────── */}
      {/* Left footing */}
      <rect
        x={wallX_L - sw(0.3)}
        y={sy(EL_FOUND_BOT)}
        width={sw(EWT + 0.6)}
        height={sw(FOUND_D)}
        fill={foundColor}
        opacity={0.7}
      />
      {/* Right footing */}
      <rect
        x={wallX_R - sw(EWT + 0.3)}
        y={sy(EL_FOUND_BOT)}
        width={sw(EWT + 0.6)}
        height={sw(FOUND_D)}
        fill={foundColor}
        opacity={0.7}
      />

      {/* ── Left external wall ────────────────────────────────────── */}
      <rect
        x={wallX_L}
        y={sy(EL_FF_TOP)}
        width={sw(EWT)}
        height={sy(EL_GL) - sy(EL_FF_TOP)}
        fill={wallColor}
        opacity={0.85}
      />
      {/* ── Right external wall ───────────────────────────────────── */}
      <rect
        x={wallX_R - sw(EWT)}
        y={sy(EL_FF_TOP)}
        width={sw(EWT)}
        height={sy(EL_GL) - sy(EL_FF_TOP)}
        fill={wallColor}
        opacity={0.85}
      />

      {/* ── Ground floor slab (between GF and FF) ────────────────── */}
      <rect
        x={wallX_L}
        y={sy(EL_FF_SLAB_TOP)}
        width={bPx}
        height={sw(SLAB_T)}
        fill={slabColor}
        opacity={0.9}
      />

      {/* ── Roof slab ─────────────────────────────────────────────── */}
      <rect
        x={wallX_L}
        y={sy(EL_ROOF_TOP)}
        width={bPx}
        height={sw(SLAB_T)}
        fill={slabColor}
        opacity={0.9}
      />

      {/* ── Parapet (left + right + top) ─────────────────────────── */}
      {/* Left parapet */}
      <rect
        x={wallX_L}
        y={sy(EL_PARAPET_TOP)}
        width={sw(EWT)}
        height={sw(PARAPET_H)}
        fill={wallColor}
        opacity={0.7}
      />
      {/* Right parapet */}
      <rect
        x={wallX_R - sw(EWT)}
        y={sy(EL_PARAPET_TOP)}
        width={sw(EWT)}
        height={sw(PARAPET_H)}
        fill={wallColor}
        opacity={0.7}
      />

      {/* ── Staircase profile ─────────────────────────────────────── */}
      {sw(treadW) > 2 && sy(0) - stairY0 > 10 && (
        <path d={buildStairPath()} fill="#CBD5E1" stroke="#64748B" strokeWidth={0.8} />
      )}

      {/* ── Ground level line ─────────────────────────────────────── */}
      <line
        x1={ox - 14}
        y1={sy(EL_GL)}
        x2={ox + bPx + 14}
        y2={sy(EL_GL)}
        stroke={groundColor}
        strokeWidth={1.5}
        strokeDasharray="4 3"
      />
      <text
        x={ox - 16}
        y={sy(EL_GL) + 3}
        textAnchor="end"
        fontSize={8}
        fill={groundColor}
        fontFamily="sans-serif"
      >
        GL
      </text>

      {/* ── Elevation labels (right side) ─────────────────────────── */}
      {[
        { el: EL_GL, label: "±0.00" },
        { el: EL_GF_TOP, label: `+${fmt(EL_GF_TOP)}` },
        { el: EL_FF_SLAB_TOP, label: `+${fmt(EL_FF_SLAB_TOP)}` },
        { el: EL_FF_TOP, label: `+${fmt(EL_FF_TOP)}` },
        { el: EL_ROOF_TOP, label: `+${fmt(EL_ROOF_TOP)}` },
        { el: EL_PARAPET_TOP, label: `+${fmt(EL_PARAPET_TOP)}` },
      ].map(({ el, label }) => (
        <g key={label}>
          <line
            x1={wallX_R + 4}
            y1={sy(el)}
            x2={wallX_R + 36}
            y2={sy(el)}
            stroke={dimColor}
            strokeWidth={0.5}
          />
          <text
            x={wallX_R + 40}
            y={sy(el) + 3}
            fontSize={8}
            fill={textColor}
            fontFamily="sans-serif"
          >
            {label} m
          </text>
        </g>
      ))}

      {/* ── Height callout labels (left side) ────────────────────── */}
      {[
        { y1: EL_GL, y2: EL_GF_TOP, label: `GF  ${GF_H.toFixed(1)} m` },
        { y1: EL_FF_SLAB_TOP, y2: EL_FF_TOP, label: `FF  ${FF_H.toFixed(1)} m` },
      ].map(({ y1, y2, label }) => {
        const midY = sy((y1 + y2) / 2);
        return (
          <g key={label}>
            <line
              x1={wallX_L - 22}
              y1={sy(y1)}
              x2={wallX_L - 22}
              y2={sy(y2)}
              stroke={dimColor}
              strokeWidth={0.6}
            />
            <line
              x1={wallX_L - 26}
              y1={sy(y1)}
              x2={wallX_L - 18}
              y2={sy(y1)}
              stroke={dimColor}
              strokeWidth={0.6}
            />
            <line
              x1={wallX_L - 26}
              y1={sy(y2)}
              x2={wallX_L - 18}
              y2={sy(y2)}
              stroke={dimColor}
              strokeWidth={0.6}
            />
            <text
              x={wallX_L - 28}
              y={midY + 3}
              textAnchor="end"
              fontSize={8}
              fill={textColor}
              fontFamily="sans-serif"
            >
              {label}
            </text>
          </g>
        );
      })}

      {/* ── Zone labels inside section ────────────────────────────── */}
      {[
        {
          label: "Ground Floor",
          y1: EL_GL,
          y2: EL_GF_TOP,
          fill: "#FEF9C3",
          opacity: 0.4,
        },
        {
          label: "First Floor",
          y1: EL_FF_SLAB_TOP,
          y2: EL_FF_TOP,
          fill: "#EDE9FE",
          opacity: 0.4,
        },
      ].map(({ label, y1, y2, fill, opacity }) => (
        <g key={label}>
          <rect
            x={wallX_L + sw(EWT)}
            y={sy(y2)}
            width={bPx - sw(2 * EWT)}
            height={sy(y1) - sy(y2)}
            fill={fill}
            opacity={opacity}
          />
          <text
            x={wallX_L + bPx / 2}
            y={(sy(y1) + sy(y2)) / 2 + 4}
            textAnchor="middle"
            fontSize={Math.max(9, Math.min(13, bPx / 10))}
            fontFamily="sans-serif"
            fontWeight="600"
            fill="#4B5563"
          >
            {label}
          </text>
        </g>
      ))}

      {/* ── Width dimension ──────────────────────────────────────────*/}
      <g stroke={dimColor} fill={dimColor} strokeWidth={0.5}>
        <line x1={wallX_L} y1={sy(EL_GL) + 18} x2={wallX_R} y2={sy(EL_GL) + 18} />
        <line x1={wallX_L} y1={sy(EL_GL) + 14} x2={wallX_L} y2={sy(EL_GL) + 22} />
        <line x1={wallX_R} y1={sy(EL_GL) + 14} x2={wallX_R} y2={sy(EL_GL) + 22} />
        <text
          x={(wallX_L + wallX_R) / 2}
          y={sy(EL_GL) + 32}
          textAnchor="middle"
          fontSize={9}
          fontFamily="sans-serif"
          stroke="none"
        >
          {buildingWidth.toFixed(2)} m
        </text>
      </g>

      {/* ── Title ─────────────────────────────────────────────────── */}
      <text
        x={VP_W / 2}
        y={14}
        textAnchor="middle"
        fontSize={10}
        fontFamily="sans-serif"
        fontWeight="600"
        fill="#1E293B"
      >
        Section A–A · G+1 Residential · Scale approx. 1:{Math.round(1 / (scale * 0.001))}
      </text>

      {/* ── Legend ───────────────────────────────────────────────── */}
      <g transform={`translate(${PAD_X}, ${VP_H - 18})`}>
        <rect x={0} y={-9} width={12} height={9} fill={wallColor} opacity={0.85} />
        <text x={16} y={0} fontSize={8} fill={textColor} fontFamily="sans-serif">
          Masonry wall
        </text>
        <rect x={80} y={-9} width={12} height={9} fill={slabColor} opacity={0.9} />
        <text x={96} y={0} fontSize={8} fill={textColor} fontFamily="sans-serif">
          RCC slab
        </text>
        <rect x={148} y={-9} width={12} height={9} fill={foundColor} opacity={0.7} />
        <text x={164} y={0} fontSize={8} fill={textColor} fontFamily="sans-serif">
          Foundation (schematic)
        </text>
        <rect x={276} y={-9} width={12} height={9} fill="#CBD5E1" opacity={1} />
        <text x={292} y={0} fontSize={8} fill={textColor} fontFamily="sans-serif">
          Staircase
        </text>
      </g>
    </svg>
  );
}
