"use client";

import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";

interface AnimatedFloorPlanProps {
  className?: string;
}

// Layout A — Front Staircase, 2BHK — dark-mode color palette
const ROOMS = [
  {
    id: "living",
    x: 32, y: 32, w: 176, h: 166, fill: "#1e40af", opacity: 0.28,
    label: "Living Room", lx: 120, ly: 118, text: "#93c5fd",
  },
  {
    id: "bed1",
    x: 212, y: 32, w: 176, h: 86, fill: "#166534", opacity: 0.28,
    label: "Bedroom 1", lx: 300, ly: 72, text: "#86efac",
  },
  {
    id: "stair",
    x: 212, y: 122, w: 176, h: 76, fill: "#78350f", opacity: 0.28,
    label: "Staircase", lx: 300, ly: 162, text: "#fcd34d",
  },
  {
    id: "bed2",
    x: 32, y: 202, w: 256, h: 86, fill: "#9f1239", opacity: 0.28,
    label: "Bedroom 2", lx: 140, ly: 248, text: "#fda4af",
  },
  {
    id: "bath",
    x: 292, y: 202, w: 96, h: 86, fill: "#4c1d95", opacity: 0.28,
    label: "Bathroom", lx: 340, ly: 248, text: "#c4b5fd",
  },
];

const COLUMNS: [number, number][] = [
  [30, 30],   [210, 30],  [390, 30],
  [30, 200],  [210, 200], [390, 200],
  [30, 290],  [290, 290], [390, 290],
];

const WINDOWS = [
  { id: "win-n1", x: 80,  y: 28, w: 60, h: 4 },
  { id: "win-n2", x: 240, y: 28, w: 60, h: 4 },
  { id: "win-w1", x: 26,  y: 90, w: 4,  h: 60 },
];

export function AnimatedFloorPlan({ className }: AnimatedFloorPlanProps) {
  const prefersReduced = useReducedMotion();

  // Helper: return 0 delay/duration if user prefers reduced motion
  const d = (t: number) => (prefersReduced ? 0 : t);
  const dur = (t: number) => (prefersReduced ? 0 : t);

  // Reusable wall animation props factory
  // Uses pathLength to "draw" the stroke from start to end
  const wall = (delay: number, duration = 0.75) => ({
    initial: { pathLength: 0, opacity: 0 } as const,
    animate: { pathLength: 1, opacity: 1 } as const,
    transition: {
      pathLength: { duration: dur(duration), delay: d(delay), ease: "easeInOut" as const },
      opacity: { duration: 0.1, delay: d(delay) },
    },
  });

  return (
    <svg
      viewBox="0 0 420 320"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("w-full h-full", className)}
      style={{ fontFamily: "monospace" }}
      aria-label="Animated floor plan — Layout A, Front Staircase, 2BHK"
      role="img"
    >
      {/* ── Background ─────────────────────────────────────── */}
      <rect width="420" height="320" fill="#080e1c" rx="8" />

      {/* ── Room fills — fade in before walls overlay them ── */}
      {ROOMS.map((r, i) => (
        <motion.rect
          key={r.id}
          x={r.x} y={r.y} width={r.w} height={r.h}
          fill={r.fill}
          initial={{ opacity: 0 }}
          animate={{ opacity: r.opacity }}
          transition={{ duration: dur(0.5), delay: d(0.55 + i * 0.12) }}
        />
      ))}

      {/* ── Staircase hatching ── */}
      <motion.g
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: dur(0.3), delay: d(0.92) }}
      >
        {[123, 134, 145, 156, 167, 178, 189].map((y) => (
          <line
            key={y}
            x1="213"
            y1={y}
            x2="388"
            y2={y}
            stroke="#f97316"
            strokeWidth="0.6"
            strokeOpacity="0.35"
            strokeDasharray="4 4"
          />
        ))}
      </motion.g>

      {/* ── Outer wall — draws first via pathLength ── */}
      <motion.path
        d="M30,30 L390,30 L390,290 L30,290 Z"
        fill="none"
        stroke="#60a5fa"
        strokeWidth={4}
        strokeLinecap="round"
        strokeLinejoin="round"
        {...wall(0, 0.9)}
      />

      {/* ── Internal walls — staggered after outer ── */}
      {/* Vertical centre wall */}
      <motion.line
        x1={210} y1={30} x2={210} y2={200}
        stroke="#60a5fa" strokeWidth={2} strokeLinecap="round"
        {...wall(0.62)}
      />
      {/* Horizontal mid wall */}
      <motion.line
        x1={30} y1={200} x2={390} y2={200}
        stroke="#60a5fa" strokeWidth={2} strokeLinecap="round"
        {...wall(0.74)}
      />
      {/* Bathroom divider */}
      <motion.line
        x1={290} y1={200} x2={290} y2={290}
        stroke="#60a5fa" strokeWidth={2} strokeLinecap="round"
        {...wall(0.83)}
      />
      {/* Staircase top */}
      <motion.line
        x1={210} y1={120} x2={390} y2={120}
        stroke="#60a5fa" strokeWidth={2} strokeLinecap="round"
        {...wall(0.89)}
      />

      {/* ── Window symbols ── */}
      {WINDOWS.map((win, i) => (
        <motion.rect
          key={win.id}
          x={win.x} y={win.y} width={win.w} height={win.h}
          fill="#93c5fd"
          fillOpacity={0.7}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: dur(0.3), delay: d(1.05 + i * 0.04) }}
        />
      ))}

      {/* ── Door swing arcs ── */}
      <motion.path
        d="M30 192 Q50 182 50 202"
        fill="none" stroke="#60a5fa" strokeWidth={1.2}
        {...wall(1.02, 0.4)}
      />
      <motion.path
        d="M210 192 Q230 182 230 202"
        fill="none" stroke="#60a5fa" strokeWidth={1.2}
        {...wall(1.08, 0.4)}
      />

      {/* ── Column markers — orange squares spring in ── */}
      {COLUMNS.map(([cx, cy], i) => (
        <motion.rect
          key={`col-${cx}-${cy}`}
          x={cx - 5} y={cy - 5}
          width={10} height={10}
          fill="#f97316"
          initial={{ opacity: 0, scale: 0 }}
          animate={{ opacity: 1, scale: 1 }}
          style={{ originX: `${cx}px`, originY: `${cy}px` }}
          transition={{
            duration: dur(0.35),
            delay: d(1.14 + i * 0.05),
            type: "spring",
            stiffness: 260,
            damping: 18,
          }}
        />
      ))}

      {/* ── Room labels ── */}
      {ROOMS.map((r, i) => (
        <motion.text
          key={`lbl-${r.id}`}
          x={r.lx} y={r.ly}
          textAnchor="middle"
          fontSize={10}
          fill={r.text}
          fontWeight={600}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: dur(0.4), delay: d(0.87 + i * 0.1) }}
        >
          {r.label}
        </motion.text>
      ))}

      {/* ── Dimension lines ── */}
      <motion.g
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: dur(0.4), delay: d(1.58) }}
      >
        <line x1="30" y1="297" x2="390" y2="297" stroke="#334155" strokeWidth="0.8" />
        <text x="210" y="305" textAnchor="middle" fontSize={8} fill="#64748b">
          9.0 m
        </text>
        <line x1="14" y1="30" x2="14" y2="290" stroke="#334155" strokeWidth="0.8" />
        <text
          x="10"
          y="165"
          textAnchor="middle"
          fontSize={8}
          fill="#64748b"
          transform="rotate(-90 10 165)"
        >
          6.5 m
        </text>
      </motion.g>

      {/* ── North arrow — orange, fades in last ── */}
      <motion.g
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: dur(0.5), delay: d(1.78) }}
      >
        <circle cx="380" cy="18" r="11" fill="#080e1c" stroke="#f97316" strokeWidth="1" />
        <polygon points="380,6 383,18 380,15 377,18" fill="#f97316" />
        <text
          x="380"
          y="32"
          textAnchor="middle"
          fontSize={8}
          fill="#f97316"
          fontWeight={700}
        >
          N
        </text>
      </motion.g>

      {/* ── Title block ── */}
      <motion.g
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: dur(0.4), delay: d(1.88) }}
      >
        <line x1="30" y1="311" x2="390" y2="311" stroke="#1e293b" strokeWidth="0.5" />
        <text x="210" y="318" textAnchor="middle" fontSize={7} fill="#475569">
          PlanForge — Ground Floor — Scale 1:100
        </text>
      </motion.g>
    </svg>
  );
}
