import { Building2, FileText, LayoutGrid, ShieldCheck } from "lucide-react";
import Link from "next/link";

const features = [
  { icon: ShieldCheck, label: "NBC 2016 compliance built in" },
  { icon: LayoutGrid, label: "5 layout variations per plot" },
  { icon: FileText, label: "PDF, DXF, and BOQ export" },
];

const COLUMNS: [number, number][] = [
  [15, 10],
  [120, 10],
  [225, 10],
  [15, 105],
  [120, 105],
  [225, 105],
  [15, 155],
  [168, 155],
  [225, 155],
];

const rooms = [
  { x: 63, y: 58, label: "Living" },
  { x: 172, y: 56, label: "Bedroom" },
  { x: 88, y: 131, label: "Kitchen" },
  { x: 196, y: 131, label: "Bath" },
];

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-background">
      {/* ── Left brand panel (lg+) ────────────────────────────── */}
      <aside className="hidden lg:flex lg:w-[46%] xl:w-[44%] flex-col bg-card border-r border-border/60 relative overflow-hidden">
        {/* Technical grid overlay */}
        <div className="absolute inset-0 bg-technical-grid" />
        {/* Ambient amber glow */}
        <div className="absolute -top-48 -left-48 w-[500px] h-[500px] rounded-full bg-[#f97316] opacity-[0.04] blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 right-0 w-80 h-80 rounded-full bg-[#f97316] opacity-[0.025] blur-3xl pointer-events-none" />

        <div className="relative flex flex-col h-full p-10 xl:p-12">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5 w-fit group">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-orange-500 to-amber-600 shadow-lg shadow-orange-500/25 transition-all group-hover:scale-105">
              <Building2 className="h-4 w-4 text-white" />
            </div>
            <span
              className="text-xl font-bold tracking-tight"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Plan<span className="text-[#f97316]">Forge</span>
            </span>
          </Link>

          {/* Centre content */}
          <div className="flex-1 flex flex-col justify-center pt-6 pb-4">
            <p className="text-xs font-bold text-[#f97316] uppercase tracking-[0.2em] mb-4">
              For Indian Builders
            </p>
            <h2
              className="text-3xl xl:text-[2.25rem] font-black text-foreground leading-[1.12] mb-5"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Plot dimensions in.
              <br />
              Floor plans <span className="text-[#f97316]">out.</span>
            </h2>
            <p className="text-sm text-muted-foreground leading-relaxed mb-8 max-w-xs">
              Generate NBC 2016–compliant G+1 residential layouts with export-ready PDF and DXF
              files — in seconds.
            </p>

            <ul className="space-y-3.5">
              {features.map(({ icon: Icon, label }) => (
                <li key={label} className="flex items-center gap-3 text-sm">
                  <div className="flex h-6 w-6 items-center justify-center rounded-md bg-[#f97316]/10 ring-1 ring-[#f97316]/20 flex-shrink-0">
                    <Icon className="h-3.5 w-3.5 text-[#f97316]" />
                  </div>
                  <span className="text-muted-foreground">{label}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Mini floor plan */}
          <div className="rounded-xl border border-border/50 overflow-hidden bg-background/50">
            <div className="flex items-center gap-1.5 px-3 py-2 border-b border-border/40">
              <span className="h-2 w-2 rounded-full bg-red-500/50" />
              <span className="h-2 w-2 rounded-full bg-yellow-500/50" />
              <span className="h-2 w-2 rounded-full bg-green-500/50" />
              <span
                className="text-[10px] text-muted-foreground/50 ml-1"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                Layout A · Bangalore · 2BHK
              </span>
            </div>
            <div className="p-3">
              <svg viewBox="0 0 240 165" className="w-full h-auto" aria-hidden="true">
                <rect width="240" height="165" fill="transparent" />
                {/* Outer wall */}
                <rect
                  x="15"
                  y="10"
                  width="210"
                  height="145"
                  fill="none"
                  stroke="#f97316"
                  strokeWidth="1.5"
                  strokeOpacity="0.45"
                />
                {/* Internal walls */}
                <line
                  x1="120"
                  y1="10"
                  x2="120"
                  y2="105"
                  stroke="#f97316"
                  strokeWidth="0.75"
                  strokeOpacity="0.3"
                />
                <line
                  x1="15"
                  y1="105"
                  x2="225"
                  y2="105"
                  stroke="#f97316"
                  strokeWidth="0.75"
                  strokeOpacity="0.3"
                />
                <line
                  x1="168"
                  y1="105"
                  x2="168"
                  y2="155"
                  stroke="#f97316"
                  strokeWidth="0.75"
                  strokeOpacity="0.3"
                />
                {/* Room tints */}
                <rect x="16" y="11" width="103" height="93" fill="#f97316" fillOpacity="0.04" />
                <rect x="121" y="11" width="103" height="93" fill="#f97316" fillOpacity="0.04" />
                <rect x="16" y="106" width="151" height="48" fill="#f97316" fillOpacity="0.04" />
                <rect x="169" y="106" width="55" height="48" fill="#f97316" fillOpacity="0.03" />
                {/* Room labels */}
                {rooms.map(({ x, y, label }) => (
                  <text
                    key={label}
                    x={x}
                    y={y}
                    textAnchor="middle"
                    fontSize="7"
                    fill="#f97316"
                    fillOpacity="0.6"
                    fontWeight="500"
                  >
                    {label}
                  </text>
                ))}
                {/* Column markers */}
                {COLUMNS.map(([cx, cy]) => (
                  <rect
                    key={`${cx}-${cy}`}
                    x={cx - 3}
                    y={cy - 3}
                    width="6"
                    height="6"
                    fill="#f97316"
                    fillOpacity="0.5"
                  />
                ))}
                {/* Dimension line */}
                <line
                  x1="15"
                  y1="162"
                  x2="225"
                  y2="162"
                  stroke="#f97316"
                  strokeWidth="0.4"
                  strokeOpacity="0.3"
                />
                <text
                  x="120"
                  y="165"
                  textAnchor="middle"
                  fontSize="5.5"
                  fill="#f97316"
                  fillOpacity="0.4"
                >
                  9.0 m
                </text>
              </svg>
            </div>
          </div>

          <p className="text-xs text-muted-foreground/35 mt-5">
            © {new Date().getFullYear()} PlanForge. Trusted by builders across India.
          </p>
        </div>
      </aside>

      {/* ── Right form panel ──────────────────────────────────── */}
      <div className="flex flex-1 items-center justify-center px-6 py-16 relative overflow-hidden">
        <div className="absolute inset-0 bg-blueprint-grid opacity-[0.18]" />
        <div className="relative w-full max-w-sm">{children}</div>
      </div>
    </div>
  );
}
