import {
  ArrowRight,
  CheckCircle,
  Download,
  Eye,
  FileSpreadsheet,
  FileText,
  Settings2,
  Zap,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { JsonLd } from "@/components/json-ld";
import { FadeIn } from "@/components/motion/fade-in";
import { SlideIn } from "@/components/motion/slide-in";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "How PlanForge Works — G+1 Floor Plan Generation in 4 Steps",
  description:
    "Enter your plot dimensions, road-facing direction, and BHK count — PlanForge generates 5 NBC 2016-compliant G+1 layout variations in under 1 second. Export as PDF, DXF, or BOQ Excel.",
  openGraph: {
    title: "How PlanForge Works — From Plot to Floor Plan in Under a Second",
    description:
      "4-step walkthrough: enter plot details → instant NBC-compliant layouts → review in browser → export PDF/DXF/BOQ. Built for Indian civil engineers.",
  },
  alternates: { canonical: "/how-it-works" },
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
      <div className="rounded-xl border border-border bg-card shadow-xl shadow-black/30 p-6 space-y-4">
        <p className="text-xs font-bold text-muted-foreground/60 uppercase tracking-widest">
          Plot Details
        </p>
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
              <span className="text-xs text-muted-foreground/60">{label}</span>
              <span className="text-sm font-semibold text-foreground">{val}</span>
            </div>
          ))}
        </div>
        <div className="pt-2">
          <Button className="w-full bg-primary hover:bg-primary/90 text-primary-foreground font-bold text-sm">
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
      <div className="rounded-xl border border-border bg-card shadow-xl shadow-black/30 p-5 space-y-3">
        <p className="text-xs font-bold text-muted-foreground/60 uppercase tracking-widest">
          Generated Layouts
        </p>
        {[
          "A — Front Staircase",
          "B — Centre Staircase",
          "C — Rear Staircase",
          "D — Corner Entry",
          "E — Open Plan",
        ].map((name) => (
          <div
            key={name}
            className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/30 px-3 py-2"
          >
            <span className="text-sm font-medium text-foreground">{name}</span>
            <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/25 text-xs">
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
      <div className="rounded-xl border border-border bg-card shadow-xl shadow-black/30 p-4">
        <div className="flex gap-2 mb-3">
          <button
            type="button"
            className="px-3 py-1 rounded bg-primary text-primary-foreground text-xs font-semibold"
          >
            Ground Floor
          </button>
          <button
            type="button"
            className="px-3 py-1 rounded bg-muted text-muted-foreground text-xs font-semibold"
          >
            First Floor
          </button>
        </div>
        {/* Mini floor plan — dark-mode friendly */}
        <svg
          viewBox="0 0 200 160"
          className="w-full"
          xmlns="http://www.w3.org/2000/svg"
          aria-label="Floor plan preview"
          role="img"
        >
          <rect width="200" height="160" fill="#0d1424" rx="4" />
          <rect
            x="10"
            y="10"
            width="180"
            height="140"
            fill="none"
            stroke="#60a5fa"
            strokeWidth="2.5"
          />
          <line x1="100" y1="10" x2="100" y2="100" stroke="#60a5fa" strokeWidth="1.2" />
          <line x1="10" y1="100" x2="190" y2="100" stroke="#60a5fa" strokeWidth="1.2" />
          <rect x="12" y="12" width="86" height="86" fill="#1e40af" fillOpacity="0.3" />
          <rect x="102" y="12" width="86" height="86" fill="#166534" fillOpacity="0.3" />
          <rect x="12" y="102" width="86" height="46" fill="#9f1239" fillOpacity="0.3" />
          <rect x="102" y="102" width="86" height="46" fill="#4c1d95" fillOpacity="0.3" />
          <text x="55" y="58" textAnchor="middle" fontSize="7" fill="#93c5fd" fontWeight="600">
            Living
          </text>
          <text x="145" y="58" textAnchor="middle" fontSize="7" fill="#86efac" fontWeight="600">
            Bedroom 1
          </text>
          <text x="55" y="126" textAnchor="middle" fontSize="7" fill="#fda4af" fontWeight="600">
            Kitchen
          </text>
          <text x="145" y="126" textAnchor="middle" fontSize="7" fill="#c4b5fd" fontWeight="600">
            Bedroom 2
          </text>
          <rect x="85" y="10" width="30" height="2.5" fill="#60a5fa" />
          <polygon
            points="190,14 193,20 190,18 187,20"
            fill="#f97316"
            transform="translate(-5, 0)"
          />
          <text x="185" y="28" fontSize="6" fill="#f97316" fontWeight="700">
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
      <div className="rounded-xl border border-border bg-card shadow-xl shadow-black/30 p-5 space-y-3">
        <p className="text-xs font-bold text-muted-foreground/60 uppercase tracking-widest">
          Export Options
        </p>
        {[
          {
            icon: FileText,
            label: "PDF — 1:100 scale",
            badge: "Free",
            color: "bg-muted text-muted-foreground",
          },
          {
            icon: FileText,
            label: "DXF — 9 named layers",
            badge: "Basic+",
            color: "bg-primary/10 text-primary/70 border border-primary/20",
          },
          {
            icon: FileSpreadsheet,
            label: "BOQ Excel — 11 items",
            badge: "Pro",
            color: "bg-primary/15 text-primary border border-primary/25",
          },
        ].map(({ icon: Icon, label, badge, color }) => (
          <div
            key={label}
            className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/30 px-3 py-2.5"
          >
            <div className="flex items-center gap-2">
              <Icon className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium text-foreground">{label}</span>
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

const howToJsonLd = {
  "@context": "https://schema.org",
  "@type": "HowTo",
  name: "How to Generate an NBC-Compliant G+1 Floor Plan with PlanForge",
  description:
    "Generate 5 NBC 2016-compliant G+1 residential floor plan variations from your plot dimensions in under a second.",
  step: [
    {
      "@type": "HowToStep",
      name: "Enter Your Plot Details",
      text: "Input plot dimensions, city, setbacks on all 4 sides, road-facing direction, BHK count (1–4), and optional rooms.",
    },
    {
      "@type": "HowToStep",
      name: "Generate 5 Layout Variations",
      text: "PlanForge generates all 5 archetypes simultaneously and checks each against NBC 2016 and city-specific rules.",
    },
    {
      "@type": "HowToStep",
      name: "Review in Browser",
      text: "Inspect colour-coded rooms, double-line walls, door arcs, dimension lines, and north arrow in the interactive SVG preview.",
    },
    {
      "@type": "HowToStep",
      name: "Export PDF, DXF, or BOQ Excel",
      text: "Download a 1:100 scale PDF, AutoCAD DXF with 9 named layers, or BOQ Excel with 11 quantity line items.",
    },
  ],
  tool: [{ "@type": "HowToTool", name: "PlanForge web app — no installation required" }],
  totalTime: "PT1M",
};

export default function HowItWorksPage() {
  return (
    <div className="bg-background">
      <JsonLd data={howToJsonLd} />
      {/* Header */}
      <section className="py-20 lg:py-24 bg-gradient-to-b from-card/30 to-background border-b border-border/30">
        <FadeIn className="mx-auto max-w-4xl px-4 text-center">
          <p className="text-xs font-bold text-primary uppercase tracking-[0.2em] mb-4">
            How It Works
          </p>
          <h1
            className="text-4xl lg:text-5xl font-black text-foreground mb-4"
            style={{ fontFamily: "var(--font-display)" }}
          >
            From Plot to Plan in 4 Steps
          </h1>
          <p className="text-lg text-muted-foreground/70 leading-relaxed max-w-xl mx-auto">
            PlanForge takes your site data and delivers NBC-compliant floor plans ready for
            construction or client handover.
          </p>
        </FadeIn>
      </section>

      {/* Step sections */}
      <section className="py-20 lg:py-24">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="space-y-28 lg:space-y-32">
            {steps.map((step, i) => {
              const Icon = step.icon;
              const reverse = i % 2 !== 0;
              return (
                <div
                  key={step.num}
                  className={`grid md:grid-cols-2 gap-12 items-center ${reverse ? "md:grid-flow-col-dense" : ""}`}
                >
                  {/* Text side — slides in from the side it visually sits on */}
                  <SlideIn
                    from={reverse ? "right" : "left"}
                    className={reverse ? "lg:col-start-2" : ""}
                  >
                    <div className="flex items-center gap-3 mb-5">
                      <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary text-primary-foreground font-black text-sm shadow-lg shadow-primary/15">
                        {step.num}
                      </div>
                      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/8 ring-1 ring-primary/15">
                        <Icon className="h-5 w-5 text-primary/70" />
                      </div>
                    </div>
                    <h2
                      className="text-2xl font-black text-foreground mb-2"
                      style={{ fontFamily: "var(--font-display)" }}
                    >
                      {step.title}
                    </h2>
                    <p className="text-muted-foreground mb-6">{step.subtitle}</p>
                    <ul className="space-y-2.5">
                      {step.points.map((p) => (
                        <li key={p} className="flex items-start gap-2.5">
                          <CheckCircle className="h-4 w-4 text-primary flex-shrink-0 mt-0.5" />
                          <span className="text-sm text-foreground/80">{p}</span>
                        </li>
                      ))}
                    </ul>
                  </SlideIn>

                  {/* Visual side — slides in from the opposite direction */}
                  <SlideIn
                    from={reverse ? "left" : "right"}
                    delay={0.1}
                    className={reverse ? "lg:col-start-1" : ""}
                  >
                    {step.visual}
                  </SlideIn>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Technical specs */}
      <section className="py-20 bg-card/20 border-y border-border/30">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
          <FadeIn>
            <h2
              className="text-2xl font-extrabold text-foreground mb-8 text-center"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Technical Specifications
            </h2>
          </FadeIn>
          <FadeIn
            delay={0.1}
            className="overflow-hidden rounded-xl border border-border shadow-sm bg-card"
          >
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-primary text-primary-foreground">
                  <th className="text-left px-6 py-3 font-semibold w-1/2">Feature</th>
                  <th className="text-left px-6 py-3 font-semibold">Detail</th>
                </tr>
              </thead>
              <tbody>
                {specs.map(([feature, detail], i) => (
                  <tr key={feature} className={i % 2 === 0 ? "bg-card" : "bg-muted/20"}>
                    <td className="px-6 py-3 font-medium text-foreground">{feature}</td>
                    <td className="px-6 py-3 text-muted-foreground">{detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </FadeIn>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-20 lg:py-24 relative overflow-hidden bg-gradient-to-br from-primary/[0.06] via-card/20 to-background border-t border-border/30">
        <div className="absolute inset-0 bg-blueprint-grid opacity-40" />
        <FadeIn className="relative mx-auto max-w-3xl px-4 text-center">
          <h2
            className="text-3xl font-extrabold text-foreground mb-3"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Start planning your first project
          </h2>
          <p className="text-muted-foreground mb-8">
            Free to start. No installation. Runs in your browser.
          </p>
          <div className="flex flex-wrap justify-center gap-4">
            <Link href="/sign-up">
              <Button
                size="lg"
                className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-10 btn-shine shadow-lg shadow-primary/20"
              >
                Get Started Free
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
            <Link href="/pricing">
              <Button
                size="lg"
                variant="outline"
                className="border-border text-foreground hover:bg-muted font-semibold px-8"
              >
                View Pricing
              </Button>
            </Link>
          </div>
        </FadeIn>
      </section>
    </div>
  );
}
