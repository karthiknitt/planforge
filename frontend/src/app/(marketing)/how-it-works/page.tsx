import {
  ArrowRight,
  Building2,
  CheckCircle,
  Download,
  Eye,
  FileSpreadsheet,
  FileText,
  LayoutGrid,
  MapPin,
  Settings2,
  Zap,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "How It Works — PlanForge",
  description: "See how PlanForge generates NBC-compliant G+1 floor plans from your plot details.",
};

/* ──────────────────────────────────────────────────────────────
   Step sections (alternating layout)
────────────────────────────────────────────────────────────── */
const steps = [
  {
    num: "01",
    icon: Settings2,
    title: "Enter Your Plot",
    subtitle: "All the details that drive the layout engine",
    points: [
      "Plot length × width in metres",
      "Setbacks on all 4 sides (N/S/E/W)",
      "Road-facing direction and north orientation",
      "City (Bangalore, Chennai, Delhi, Hyderabad, Pune, or Other)",
      "Road width for FAR calculation",
      "BHK count (1, 2, 3, or 4)",
      "Optional rooms: pooja room, study, balcony",
    ],
    visual: (
      <div className="rounded-xl border border-slate-100 bg-white shadow-lg p-6 space-y-4">
        <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Plot Details</p>
        <div className="grid grid-cols-2 gap-3">
          {[
            ["Length", "9.0 m"],
            ["Width", "12.0 m"],
            ["City", "Bangalore"],
            ["BHK", "3 BHK"],
            ["Front setback", "1.5 m"],
            ["Rear setback", "1.5 m"],
            ["Road width", "9.0 m"],
            ["Optional", "Pooja, Study"],
          ].map(([label, val]) => (
            <div key={label} className="flex flex-col">
              <span className="text-xs text-slate-400">{label}</span>
              <span className="text-sm font-semibold text-[#1e3a5f]">{val}</span>
            </div>
          ))}
        </div>
        <div className="pt-2">
          <Button className="w-full bg-[#f97316] hover:bg-[#ea6c0a] text-white font-bold text-sm">
            Generate Layouts
            <Zap className="ml-2 h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    ),
  },
  {
    num: "02",
    icon: Zap,
    title: "Instant Layout Generation",
    subtitle: "5 archetypes, each NBC-checked in under a second",
    points: [
      "Layout A — Front staircase (road-facing stair)",
      "Layout B — Centre staircase (internal core)",
      "Layout C — Rear staircase (maximises front depth)",
      "Layout D — Corner entry (side-access plots)",
      "Layout E — Open-plan kitchen/dining",
      "Each layout checked against NBC 2016 room-area rules",
      "City-specific setbacks and FAR validated per Bangalore/Chennai/Delhi rules",
      "Compliance warnings shown per layout (not blocking — informational)",
    ],
    visual: (
      <div className="rounded-xl border border-slate-100 bg-white shadow-lg p-5 space-y-3">
        <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">
          Generated Layouts
        </p>
        {[
          "A — Front Staircase",
          "B — Centre Staircase",
          "C — Rear Staircase",
          "D — Corner Entry",
          "E — Open Plan",
        ].map((name, i) => (
          <div
            key={name}
            className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2"
          >
            <span className="text-sm font-medium text-[#1e3a5f]">{name}</span>
            <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200 text-xs">
              NBC ✓
            </Badge>
          </div>
        ))}
      </div>
    ),
  },
  {
    num: "03",
    icon: Eye,
    title: "Review in Browser",
    subtitle: "Interactive CAD-grade SVG preview",
    points: [
      "Colour-coded rooms for instant identification",
      "Double-line walls — 230 mm external, 115 mm internal",
      "Door swing arcs and window frame symbols",
      "Dimension lines with mm measurements",
      "Column markers at structural intersections",
      "North arrow and title block on every drawing",
      "Toggle between Ground Floor and First Floor",
      "Room labels with area in sqm",
    ],
    visual: (
      <div className="rounded-xl border border-slate-100 bg-white shadow-lg p-4">
        <div className="flex gap-2 mb-3">
          <button
            type="button"
            className="px-3 py-1 rounded bg-[#1e3a5f] text-white text-xs font-semibold"
          >
            Ground Floor
          </button>
          <button
            type="button"
            className="px-3 py-1 rounded bg-slate-100 text-slate-500 text-xs font-semibold"
          >
            First Floor
          </button>
        </div>
        {/* Mini floor plan */}
        <svg
          viewBox="0 0 200 160"
          className="w-full"
          xmlns="http://www.w3.org/2000/svg"
          aria-label="Floor plan preview"
          role="img"
        >
          <rect width="200" height="160" fill="#f8fafc" rx="4" />
          <rect
            x="10"
            y="10"
            width="180"
            height="140"
            fill="none"
            stroke="#1e3a5f"
            strokeWidth="3"
          />
          <line x1="100" y1="10" x2="100" y2="100" stroke="#1e3a5f" strokeWidth="1.5" />
          <line x1="10" y1="100" x2="190" y2="100" stroke="#1e3a5f" strokeWidth="1.5" />
          <rect x="12" y="12" width="86" height="86" fill="#dbeafe" fillOpacity="0.7" />
          <rect x="102" y="12" width="86" height="86" fill="#dcfce7" fillOpacity="0.7" />
          <rect x="12" y="102" width="86" height="46" fill="#fee2e2" fillOpacity="0.7" />
          <rect x="102" y="102" width="86" height="46" fill="#fce7f3" fillOpacity="0.7" />
          <text x="55" y="58" textAnchor="middle" fontSize="7" fill="#1e40af" fontWeight="600">
            Living
          </text>
          <text x="145" y="58" textAnchor="middle" fontSize="7" fill="#166534" fontWeight="600">
            Bedroom 1
          </text>
          <text x="55" y="126" textAnchor="middle" fontSize="7" fill="#9f1239" fontWeight="600">
            Kitchen
          </text>
          <text x="145" y="126" textAnchor="middle" fontSize="7" fill="#9d174d" fontWeight="600">
            Bedroom 2
          </text>
          <rect x="85" y="10" width="30" height="3" fill="#93c5fd" />
          <polygon
            points="190,14 193,20 190,18 187,20"
            fill="#1e3a5f"
            transform="translate(-5, 0)"
          />
          <text x="185" y="28" fontSize="6" fill="#1e3a5f" fontWeight="700">
            N
          </text>
        </svg>
      </div>
    ),
  },
  {
    num: "04",
    icon: Download,
    title: "Export & Build",
    subtitle: "Everything you need to move from screen to site",
    points: [
      "PDF — 1:100 scale, A3 or A4, with title block and dimensions",
      "DXF — AutoCAD-ready with 9 named layers (A-WALL-BRICK, A-DOOR, S-COLUMN, DIM-LINE, …)",
      "BOQ Excel — 11 quantity line items: masonry, concrete, steel, plaster, flooring, excavation",
      "Download all from the project view — no extra steps",
      "Works on Free plan (PDF only) — DXF and BOQ with Basic/Pro",
    ],
    visual: (
      <div className="rounded-xl border border-slate-100 bg-white shadow-lg p-5 space-y-3">
        <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Export Options</p>
        {[
          {
            icon: FileText,
            label: "PDF — 1:100 scale",
            badge: "Free",
            color: "bg-slate-100 text-slate-600",
          },
          {
            icon: FileText,
            label: "DXF — 9 named layers",
            badge: "Basic+",
            color: "bg-blue-50 text-blue-700",
          },
          {
            icon: FileSpreadsheet,
            label: "BOQ Excel — 11 items",
            badge: "Pro",
            color: "bg-orange-50 text-orange-700",
          },
        ].map(({ icon: Icon, label, badge, color }) => (
          <div
            key={label}
            className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2.5"
          >
            <div className="flex items-center gap-2">
              <Icon className="h-4 w-4 text-[#1e3a5f]" />
              <span className="text-sm font-medium text-[#1e3a5f]">{label}</span>
            </div>
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${color}`}>
              {badge}
            </span>
          </div>
        ))}
      </div>
    ),
  },
];

/* ──────────────────────────────────────────────────────────────
   Technical specs table
────────────────────────────────────────────────────────────── */
const specs = [
  ["Plot type", "Rectangular"],
  ["Layouts per run", "5 variations (A–E)"],
  ["BHK range", "1–4 BHK"],
  ["Compliance", "NBC 2016 + city-specific rules"],
  ["PDF scale", "1:100"],
  ["DXF layers", "9 named layers"],
  ["BOQ items", "11 quantity types"],
  ["Optional rooms", "Pooja, Study, Balcony"],
  ["Supported cities", "6 (Bangalore, Chennai, Delhi, Hyderabad, Pune, Other)"],
];

export default function HowItWorksPage() {
  return (
    <div className="bg-white">
      {/* Header */}
      <section className="py-20 bg-gradient-to-b from-slate-50 to-white border-b border-slate-100">
        <div className="mx-auto max-w-4xl px-4 text-center">
          <Badge className="mb-5 bg-[#1e3a5f]/10 text-[#1e3a5f] border-[#1e3a5f]/20 hover:bg-[#1e3a5f]/10">
            From plot to plan
          </Badge>
          <h1 className="text-4xl lg:text-5xl font-extrabold text-[#1e3a5f] mb-4">
            From Plot to Plan in 3 Steps
          </h1>
          <p className="text-xl text-slate-500 leading-relaxed">
            PlanForge takes your site data and delivers NBC-compliant floor plans ready for
            construction or client handover.
          </p>
        </div>
      </section>

      {/* Step sections */}
      <section className="py-16">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="space-y-24">
            {steps.map((step, i) => {
              const Icon = step.icon;
              const reverse = i % 2 !== 0;
              return (
                <div
                  key={step.num}
                  className={`grid lg:grid-cols-2 gap-12 items-center ${reverse ? "lg:grid-flow-col-dense" : ""}`}
                >
                  {/* Text side */}
                  <div className={reverse ? "lg:col-start-2" : ""}>
                    <div className="flex items-center gap-3 mb-4">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#1e3a5f] text-white font-extrabold text-sm">
                        {step.num}
                      </div>
                      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#f97316]/10">
                        <Icon className="h-5 w-5 text-[#f97316]" />
                      </div>
                    </div>
                    <h2 className="text-2xl font-extrabold text-[#1e3a5f] mb-1">{step.title}</h2>
                    <p className="text-slate-500 mb-6">{step.subtitle}</p>
                    <ul className="space-y-2.5">
                      {step.points.map((p) => (
                        <li key={p} className="flex items-start gap-2.5">
                          <CheckCircle className="h-4 w-4 text-[#f97316] flex-shrink-0 mt-0.5" />
                          <span className="text-sm text-slate-700">{p}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Visual side */}
                  <div className={reverse ? "lg:col-start-1" : ""}>{step.visual}</div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Technical specs */}
      <section className="py-16 bg-slate-50 border-y border-slate-100">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
          <h2 className="text-2xl font-extrabold text-[#1e3a5f] mb-8 text-center">
            Technical Specifications
          </h2>
          <div className="overflow-hidden rounded-xl border border-slate-200 shadow-sm bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-[#1e3a5f] text-white">
                  <th className="text-left px-6 py-3 font-semibold w-1/2">Feature</th>
                  <th className="text-left px-6 py-3 font-semibold">Detail</th>
                </tr>
              </thead>
              <tbody>
                {specs.map(([feature, detail], i) => (
                  <tr key={feature} className={i % 2 === 0 ? "bg-white" : "bg-slate-50"}>
                    <td className="px-6 py-3 font-medium text-[#1e3a5f]">{feature}</td>
                    <td className="px-6 py-3 text-slate-600">{detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-20 bg-[#1e3a5f]">
        <div className="mx-auto max-w-3xl px-4 text-center">
          <h2 className="text-3xl font-extrabold text-white mb-3">
            Start planning your first project
          </h2>
          <p className="text-slate-300 mb-8">
            Free to start. No installation. Runs in your browser.
          </p>
          <div className="flex flex-wrap justify-center gap-4">
            <Link href="/sign-up">
              <Button
                size="lg"
                className="bg-[#f97316] hover:bg-[#ea6c0a] text-white font-bold px-10"
              >
                Get Started Free
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
            <Link href="/pricing">
              <Button
                size="lg"
                variant="outline"
                className="border-white text-white hover:bg-white/10 font-semibold px-8"
              >
                View Pricing
              </Button>
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
