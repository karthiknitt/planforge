import {
  ArrowRight,
  Building2,
  CheckCircle,
  FileText,
  LayoutGrid,
  MapPin,
  Package,
  ShieldCheck,
} from "lucide-react";
import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { auth } from "@/lib/auth";

/* ──────────────────────────────────────────────────────────────
   Mock floor-plan SVG
────────────────────────────────────────────────────────────── */
function FloorPlanSVG() {
  return (
    <svg
      viewBox="0 0 420 320"
      xmlns="http://www.w3.org/2000/svg"
      className="w-full h-full floor-plan-svg"
      style={{ fontFamily: "monospace" }}
      aria-label="Sample floor plan — Layout A front staircase"
      role="img"
    >
      {/* Background */}
      <rect width="420" height="320" fill="var(--svg-bg, #f8fafc)" rx="8" className="svg-bg" />

      {/* Outer wall */}
      <rect x="30" y="30" width="360" height="260" fill="none" stroke="#1e3a5f" strokeWidth="4" />

      {/* Internal walls */}
      {/* Vertical centre wall */}
      <line x1="210" y1="30" x2="210" y2="200" stroke="#1e3a5f" strokeWidth="2" />
      {/* Horizontal mid wall */}
      <line x1="30" y1="200" x2="390" y2="200" stroke="#1e3a5f" strokeWidth="2" />
      {/* Kitchen/Bathroom divider */}
      <line x1="290" y1="200" x2="290" y2="290" stroke="#1e3a5f" strokeWidth="2" />
      {/* Staircase box right */}
      <line x1="210" y1="120" x2="390" y2="120" stroke="#1e3a5f" strokeWidth="2" />

      {/* Room fills */}
      {/* Living Room */}
      <rect x="32" y="32" width="176" height="166" fill="#dbeafe" fillOpacity="0.6" />
      {/* Bedroom 1 */}
      <rect x="212" y="32" width="176" height="86" fill="#dcfce7" fillOpacity="0.6" />
      {/* Staircase */}
      <rect x="212" y="122" width="176" height="76" fill="#fef9c3" fillOpacity="0.8" />
      {/* Kitchen */}
      <rect x="32" y="202" width="256" height="86" fill="#fee2e2" fillOpacity="0.6" />
      {/* Bathroom */}
      <rect x="292" y="202" width="96" height="86" fill="#ede9fe" fillOpacity="0.6" />
      {/* Bedroom 2 */}
      <rect x="32" y="202" width="176" height="86" fill="#fce7f3" fillOpacity="0.6" />

      {/* Staircase hatching */}
      {[0, 1, 2, 3, 4, 5, 6].map((i) => (
        <line
          key={i}
          x1="212"
          y1={122 + i * 11}
          x2={212 + 176}
          y2={122 + i * 11}
          stroke="#92400e"
          strokeWidth="0.8"
          strokeDasharray="4 4"
        />
      ))}

      {/* Door symbols */}
      <path d="M30 190 Q50 180 50 200" fill="none" stroke="#1e3a5f" strokeWidth="1.2" />
      <path d="M210 190 Q230 180 230 200" fill="none" stroke="#1e3a5f" strokeWidth="1.2" />

      {/* Window symbols on outer wall */}
      <rect x="80" y="28" width="60" height="4" fill="#93c5fd" />
      <rect x="240" y="28" width="60" height="4" fill="#93c5fd" />
      <rect x="26" y="90" width="4" height="60" fill="#93c5fd" />

      {/* Column markers */}
      {[
        [30, 30],
        [210, 30],
        [390, 30],
        [30, 200],
        [210, 200],
        [390, 200],
        [30, 290],
        [290, 290],
        [390, 290],
      ].map(([cx, cy]) => (
        <rect key={`col-${cx}-${cy}`} x={cx - 5} y={cy - 5} width="10" height="10" fill="#1e3a5f" />
      ))}

      {/* Room labels */}
      <text x="118" y="118" textAnchor="middle" fontSize="11" fill="#1e40af" fontWeight="600">
        Living Room
      </text>
      <text x="298" y="72" textAnchor="middle" fontSize="11" fill="#166534" fontWeight="600">
        Bedroom 1
      </text>
      <text x="298" y="162" textAnchor="middle" fontSize="11" fill="#92400e" fontWeight="600">
        Staircase
      </text>
      <text x="130" y="248" textAnchor="middle" fontSize="11" fill="#9f1239" fontWeight="600">
        Bedroom 2
      </text>
      <text x="340" y="248" textAnchor="middle" fontSize="11" fill="#5b21b6" fontWeight="600">
        Bathroom
      </text>

      {/* Dimension lines */}
      <line
        x1="30"
        y1="310"
        x2="390"
        y2="310"
        stroke="#64748b"
        strokeWidth="1"
        markerEnd="url(#arr)"
      />
      <text x="210" y="318" textAnchor="middle" fontSize="9" fill="#64748b">
        9.0 m
      </text>
      <line x1="10" y1="30" x2="10" y2="290" stroke="#64748b" strokeWidth="1" />
      <text
        x="6"
        y="165"
        textAnchor="middle"
        fontSize="9"
        fill="#64748b"
        transform="rotate(-90 6 165)"
      >
        6.5 m
      </text>

      {/* North arrow */}
      <g transform="translate(390, 20)">
        <polygon points="0,-12 4,4 0,0 -4,4" fill="#1e3a5f" />
        <text x="0" y="14" textAnchor="middle" fontSize="9" fill="#1e3a5f" fontWeight="700">
          N
        </text>
      </g>

      {/* Title block */}
      <rect x="30" y="305" width="360" height="1" fill="#cbd5e1" />
      <text x="210" y="314" textAnchor="middle" fontSize="8" fill="#94a3b8">
        PlanForge — Ground Floor — Scale 1:100
      </text>
    </svg>
  );
}

/* ──────────────────────────────────────────────────────────────
   Feature cards
────────────────────────────────────────────────────────────── */
const features = [
  {
    icon: ShieldCheck,
    title: "NBC 2016 Compliance",
    desc: "Automatic setback, FAR, and room-size checks for Bangalore, Chennai, Delhi, Hyderabad, Pune.",
  },
  {
    icon: LayoutGrid,
    title: "5 Layout Variations",
    desc: "Front, centre, rear, corner, and open-plan archetypes generated instantly from your plot dimensions.",
  },
  {
    icon: FileText,
    title: "CAD-Grade Export",
    desc: "PDF at 1:100 scale with dimensions, north arrow, title block. DXF with 9 named layers for AutoCAD.",
  },
  {
    icon: Package,
    title: "Bill of Quantities",
    desc: "Auto-calculated masonry, concrete, steel, and flooring quantities. Export to Excel.",
  },
  {
    icon: Building2,
    title: "1-4 BHK Support",
    desc: "From compact 1BHK to spacious 4BHK. Optional pooja room, study, and balcony.",
  },
  {
    icon: MapPin,
    title: "City-Specific Rules",
    desc: "Setback tables and FAR limits for 6 major Indian cities baked in.",
  },
];

/* ──────────────────────────────────────────────────────────────
   Steps
────────────────────────────────────────────────────────────── */
const steps = [
  {
    num: "01",
    title: "Enter Plot Details",
    desc: "Input dimensions, city, setbacks on all 4 sides, road-facing direction, BHK count, and optional rooms.",
  },
  {
    num: "02",
    title: "Get 5 Layouts",
    desc: "Engine generates all archetypes simultaneously and checks each against NBC + city-specific rules.",
  },
  {
    num: "03",
    title: "Export & Build",
    desc: "Download PDF, DXF for AutoCAD, or BOQ Excel — all from a single click.",
  },
];

/* ──────────────────────────────────────────────────────────────
   Pricing
────────────────────────────────────────────────────────────── */
const plans = [
  {
    name: "Free",
    price: "\u20B90",
    period: "/month",
    perks: ["3 projects", "PDF export"],
    cta: "Get Started",
    highlight: false,
  },
  {
    name: "Basic",
    price: "\u20B9499",
    period: "/month",
    perks: ["Unlimited projects", "PDF + DXF export"],
    cta: "Subscribe",
    highlight: true,
  },
  {
    name: "Pro",
    price: "\u20B9999",
    period: "/month",
    perks: ["Everything in Basic", "BOQ Excel export", "Priority support"],
    cta: "Subscribe",
    highlight: false,
  },
];

/* ──────────────────────────────────────────────────────────────
   Page
────────────────────────────────────────────────────────────── */
export const metadata: Metadata = {
  title: "G+1 Floor Plan Generator for Indian Builders",
  description:
    "Input plot dimensions, get 5 NBC-compliant layout variations instantly — PDF, DXF, BOQ export.",
  openGraph: {
    title: "PlanForge — G+1 Floor Plan Generator",
    description:
      "Input plot dimensions, get 5 NBC-compliant layout variations instantly — PDF, DXF, BOQ export.",
  },
};

export default async function LandingPage() {
  const session = await auth.api.getSession({ headers: await headers() });
  if (session) redirect("/dashboard");

  return (
    <>
      {/* ── HERO ── */}
      <section className="relative overflow-hidden bg-background border-b border-border/50 min-h-[85vh] flex items-center">
        {/* Blueprint grid overlay */}
        <div className="absolute inset-0 bg-blueprint-grid opacity-100" />
        {/* Radial glow */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_15%_60%,rgba(249,115,22,0.07)_0%,transparent_55%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_85%_15%,rgba(249,115,22,0.10)_0%,transparent_50%)]" />

        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-20 lg:py-28 w-full">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            {/* Left: copy with stagger animations */}
            <div>
              <div className="animate-fade-up delay-100">
                <Badge className="mb-5 bg-primary/10 text-primary border-primary/25 hover:bg-primary/15">
                  NBC 2016 Compliant
                </Badge>
              </div>
              <h1
                className="animate-fade-up delay-200 text-5xl lg:text-6xl font-black tracking-tight text-foreground leading-[1.08] mb-6"
                style={{ fontFamily: "var(--font-display)" }}
              >
                Generate G+1
                <br />
                Floor Plans
                <br />
                <span className="text-gradient-orange">in Seconds</span>
              </h1>
              <p className="animate-fade-up delay-300 text-lg text-muted-foreground mb-8 leading-relaxed max-w-lg">
                Input your plot dimensions, get 5 layout variations instantly — each NBC-compliant,
                export-ready as PDF or DXF. Built for Indian civil engineers and small builders.
              </p>
              <div className="animate-fade-up delay-400 flex flex-wrap gap-4">
                <Link href="/sign-up">
                  <Button
                    size="lg"
                    className="bg-[#f97316] hover:bg-[#ea6c0a] text-white font-bold px-8 btn-shine shadow-lg shadow-orange-500/20"
                  >
                    Start Free
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                </Link>
                <Link href="/how-it-works">
                  <Button
                    size="lg"
                    variant="outline"
                    className="border-border text-foreground hover:bg-muted font-semibold px-8"
                  >
                    See How It Works
                  </Button>
                </Link>
              </div>
              <p className="animate-fade-up delay-500 mt-4 text-sm text-muted-foreground/60">
                No credit card required -- Free forever plan available
              </p>
            </div>

            {/* Right: floor plan preview */}
            <div className="animate-scale-in delay-300 relative">
              <div className="rounded-2xl border border-border/60 shadow-2xl shadow-black/40 overflow-hidden bg-card">
                <div className="px-4 pt-3 pb-2 border-b border-border/50 bg-muted/30 flex items-center gap-2">
                  <div className="flex gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-full bg-red-500/70" />
                    <span className="h-2.5 w-2.5 rounded-full bg-yellow-500/70" />
                    <span className="h-2.5 w-2.5 rounded-full bg-green-500/70" />
                  </div>
                  <span
                    className="text-xs font-medium text-muted-foreground/70 ml-1"
                    style={{ fontFamily: "var(--font-mono)" }}
                  >
                    Layout A -- Front Staircase -- 2BHK -- Bangalore
                  </span>
                </div>
                <div className="p-3">
                  <FloorPlanSVG />
                </div>
              </div>
              <div className="absolute -top-3 -right-3 bg-[#f97316] text-white text-xs font-bold px-3 py-1.5 rounded-full shadow-lg shadow-orange-500/30 animate-float">
                5 layouts
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── FEATURES ── */}
      <section className="py-24 bg-background relative">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_0%,rgba(249,115,22,0.04)_0%,transparent_60%)]" />
        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2
              className="text-3xl lg:text-4xl font-bold text-foreground mb-3"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Everything you need to design & deliver
            </h2>
            <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
              From compliance checks to CAD-ready exports — in one tool.
            </p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {features.map(({ icon: Icon, title, desc }, i) => (
              <div
                key={title}
                className="feature-card rounded-2xl border border-border bg-card p-6 animate-fade-up"
                style={{ animationDelay: `${i * 80}ms` }}
              >
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 ring-1 ring-primary/20 mb-4">
                  <Icon className="h-5 w-5 text-primary" />
                </div>
                <h3
                  className="text-base font-semibold text-foreground mb-2"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  {title}
                </h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section className="py-24 bg-muted/20 border-y border-border/50">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2
              className="text-3xl lg:text-4xl font-bold text-foreground mb-3"
              style={{ fontFamily: "var(--font-display)" }}
            >
              How It Works
            </h2>
            <p className="text-muted-foreground text-lg">Three steps from plot to plan.</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            {steps.map((step, i) => (
              <div key={step.num} className="relative flex flex-col items-center text-center">
                {i < steps.length - 1 && (
                  <div className="hidden md:block absolute top-6 left-[calc(50%+2.5rem)] w-[calc(100%-5rem)] h-px bg-gradient-to-r from-primary/40 to-primary/10" />
                )}
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground font-extrabold text-lg mb-4 z-10 shadow-lg shadow-primary/20">
                  {step.num}
                </div>
                <h3
                  className="text-lg font-bold text-foreground mb-2"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  {step.title}
                </h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{step.desc}</p>
              </div>
            ))}
          </div>
          <div className="mt-10 text-center">
            <Link href="/how-it-works">
              <Button variant="outline" className="border-border text-foreground hover:bg-muted">
                Full walkthrough
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* ── PRICING PREVIEW ── */}
      <section className="py-24 bg-background relative">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_100%,rgba(249,115,22,0.05)_0%,transparent_60%)]" />
        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2
              className="text-3xl lg:text-4xl font-bold text-foreground mb-3"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Simple Pricing
            </h2>
            <p className="text-muted-foreground text-lg">Start free. Upgrade when you need more.</p>
          </div>
          <div className="grid md:grid-cols-3 gap-6 max-w-4xl mx-auto">
            {plans.map((plan) => (
              <div
                key={plan.name}
                className={`relative flex flex-col rounded-2xl border p-6 ${
                  plan.highlight
                    ? "glow-card border-[#f97316]/50 scale-[1.03]"
                    : "border-border bg-card"
                }`}
              >
                {plan.highlight && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-[#f97316] text-white text-xs font-bold px-4 py-1 rounded-full">
                    Most Popular
                  </div>
                )}
                <div className="mb-4">
                  <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-2">
                    {plan.name}
                  </p>
                  <div className="flex items-baseline gap-1">
                    <span
                      className="text-4xl font-black text-foreground"
                      style={{ fontFamily: "var(--font-display)" }}
                    >
                      {plan.price}
                    </span>
                    <span className="text-muted-foreground text-sm">{plan.period}</span>
                  </div>
                </div>
                <ul className="space-y-2.5 flex-1 mb-6">
                  {plan.perks.map((p) => (
                    <li key={p} className="flex items-center gap-2.5 text-sm text-muted-foreground">
                      <CheckCircle className="h-4 w-4 text-[#f97316] flex-shrink-0" />
                      {p}
                    </li>
                  ))}
                </ul>
                <Link href="/sign-up" className="block">
                  <Button
                    className={`w-full font-bold ${
                      plan.highlight
                        ? "bg-[#f97316] hover:bg-[#ea6c0a] text-white btn-shine"
                        : "bg-primary hover:bg-primary/90 text-primary-foreground"
                    }`}
                  >
                    {plan.cta}
                  </Button>
                </Link>
              </div>
            ))}
          </div>
          <p className="text-center text-sm text-muted-foreground/60 mt-6">
            <Link href="/pricing" className="text-primary hover:underline underline-offset-4">
              See full pricing details &rarr;
            </Link>
          </p>
        </div>
      </section>

      {/* ── FINAL CTA ── */}
      <section className="py-24 relative overflow-hidden bg-gradient-to-br from-[#f97316]/8 via-background to-background border-t border-border/50">
        <div className="absolute inset-0 bg-blueprint-grid opacity-50" />
        <div className="relative mx-auto max-w-3xl px-4 text-center">
          <h2
            className="text-3xl lg:text-4xl font-black text-foreground mb-3"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Ready to plan your first project?
          </h2>
          <p className="text-muted-foreground text-lg mb-8">
            Sign up free — no credit card required.
          </p>
          <Link href="/sign-up">
            <Button
              size="lg"
              className="bg-[#f97316] hover:bg-[#ea6c0a] text-white font-bold px-10 btn-shine shadow-lg shadow-orange-500/20"
            >
              Start Free
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </Link>
        </div>
      </section>
    </>
  );
}
