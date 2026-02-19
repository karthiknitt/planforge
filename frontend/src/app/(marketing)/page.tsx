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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { auth } from "@/lib/auth";

/* ──────────────────────────────────────────────────────────────
   Mock floor-plan SVG
────────────────────────────────────────────────────────────── */
function FloorPlanSVG() {
  return (
    <svg
      viewBox="0 0 420 320"
      xmlns="http://www.w3.org/2000/svg"
      className="w-full h-full"
      style={{ fontFamily: "monospace" }}
      aria-label="Sample floor plan — Layout A front staircase"
      role="img"
    >
      {/* Background */}
      <rect width="420" height="320" fill="#f8fafc" rx="8" />

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
    title: "1–4 BHK Support",
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
    price: "₹0",
    period: "/month",
    perks: ["3 projects", "PDF export"],
    cta: "Get Started",
    highlight: false,
  },
  {
    name: "Basic",
    price: "₹499",
    period: "/month",
    perks: ["Unlimited projects", "PDF + DXF export"],
    cta: "Subscribe",
    highlight: true,
  },
  {
    name: "Pro",
    price: "₹999",
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
      <section className="relative overflow-hidden bg-gradient-to-b from-slate-50 to-white border-b border-slate-100">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-20 lg:py-28">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            {/* Left: copy */}
            <div>
              <Badge className="mb-5 bg-[#1e3a5f]/10 text-[#1e3a5f] border-[#1e3a5f]/20 hover:bg-[#1e3a5f]/10">
                NBC 2016 Compliant
              </Badge>
              <h1 className="text-4xl lg:text-5xl font-extrabold tracking-tight text-[#1e3a5f] leading-tight mb-5">
                Generate G+1 Floor Plans <span className="text-[#f97316]">in Seconds</span>
              </h1>
              <p className="text-lg text-slate-600 mb-8 leading-relaxed">
                Input your plot dimensions, get 5 layout variations instantly — each NBC-compliant,
                export-ready as PDF or DXF. Built for Indian civil engineers and small builders.
              </p>
              <div className="flex flex-wrap gap-4">
                <Link href="/sign-up">
                  <Button
                    size="lg"
                    className="bg-[#f97316] hover:bg-[#ea6c0a] text-white font-bold px-8"
                  >
                    Start Free
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                </Link>
                <Link href="/how-it-works">
                  <Button
                    size="lg"
                    variant="outline"
                    className="border-[#1e3a5f] text-[#1e3a5f] hover:bg-[#1e3a5f]/5 font-semibold px-8"
                  >
                    See How It Works
                  </Button>
                </Link>
              </div>
              <p className="mt-4 text-sm text-slate-400">
                No credit card required. Free forever plan available.
              </p>
            </div>

            {/* Right: floor plan preview */}
            <div className="relative">
              <div className="rounded-xl border-2 border-[#1e3a5f]/10 shadow-2xl shadow-[#1e3a5f]/10 overflow-hidden bg-white p-4">
                <div className="text-xs font-mono text-slate-400 mb-2 flex items-center gap-2">
                  <span className="inline-block h-2 w-2 rounded-full bg-[#f97316]" />
                  Layout A — Front Staircase — 2BHK — Bangalore
                </div>
                <FloorPlanSVG />
              </div>
              {/* decorative badges */}
              <div className="absolute -top-3 -right-3 bg-[#f97316] text-white text-xs font-bold px-3 py-1 rounded-full shadow-lg">
                5 layouts
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── FEATURES ── */}
      <section className="py-20 bg-white">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-14">
            <h2 className="text-3xl font-extrabold text-[#1e3a5f] mb-3">
              Everything you need to design & deliver
            </h2>
            <p className="text-slate-500 text-lg">
              From compliance checks to CAD-ready exports — in one tool.
            </p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map(({ icon: Icon, title, desc }) => (
              <Card
                key={title}
                className="border-slate-100 shadow-sm hover:shadow-md transition-shadow"
              >
                <CardHeader className="pb-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#1e3a5f]/8">
                      <Icon className="h-5 w-5 text-[#1e3a5f]" />
                    </div>
                    <CardTitle className="text-base font-bold text-[#1e3a5f]">{title}</CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-slate-600 leading-relaxed">{desc}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section className="py-20 bg-slate-50 border-y border-slate-100">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-14">
            <h2 className="text-3xl font-extrabold text-[#1e3a5f] mb-3">How It Works</h2>
            <p className="text-slate-500 text-lg">Three steps from plot to plan.</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            {steps.map((step, i) => (
              <div key={step.num} className="relative flex flex-col items-center text-center">
                {/* connector line */}
                {i < steps.length - 1 && (
                  <div className="hidden md:block absolute top-6 left-[calc(50%+2.5rem)] w-[calc(100%-5rem)] h-px bg-[#1e3a5f]/15" />
                )}
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[#1e3a5f] text-white font-extrabold text-lg mb-4 z-10">
                  {step.num}
                </div>
                <h3 className="text-lg font-bold text-[#1e3a5f] mb-2">{step.title}</h3>
                <p className="text-sm text-slate-600 leading-relaxed">{step.desc}</p>
              </div>
            ))}
          </div>
          <div className="mt-10 text-center">
            <Link href="/how-it-works">
              <Button
                variant="outline"
                className="border-[#1e3a5f] text-[#1e3a5f] hover:bg-[#1e3a5f]/5"
              >
                Full walkthrough
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* ── PRICING PREVIEW ── */}
      <section className="py-20 bg-white">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-14">
            <h2 className="text-3xl font-extrabold text-[#1e3a5f] mb-3">Simple Pricing</h2>
            <p className="text-slate-500 text-lg">Start free. Upgrade when you need more.</p>
          </div>
          <div className="grid md:grid-cols-3 gap-6 max-w-4xl mx-auto">
            {plans.map((plan) => (
              <Card
                key={plan.name}
                className={`relative flex flex-col ${
                  plan.highlight
                    ? "border-[#f97316] shadow-xl shadow-[#f97316]/10 scale-105"
                    : "border-slate-200 shadow-sm"
                }`}
              >
                {plan.highlight && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-[#f97316] text-white text-xs font-bold px-4 py-1 rounded-full">
                    Most Popular
                  </div>
                )}
                <CardHeader className="pb-2 pt-6">
                  <p className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
                    {plan.name}
                  </p>
                  <div className="flex items-baseline gap-1 mt-1">
                    <span className="text-4xl font-extrabold text-[#1e3a5f]">{plan.price}</span>
                    <span className="text-slate-400 text-sm">{plan.period}</span>
                  </div>
                </CardHeader>
                <CardContent className="flex-1 flex flex-col gap-4">
                  <ul className="space-y-2">
                    {plan.perks.map((p) => (
                      <li key={p} className="flex items-center gap-2 text-sm text-slate-700">
                        <CheckCircle className="h-4 w-4 text-[#f97316] flex-shrink-0" />
                        {p}
                      </li>
                    ))}
                  </ul>
                  <div className="mt-auto pt-2">
                    <Link href="/sign-up" className="block">
                      <Button
                        className={`w-full font-bold ${
                          plan.highlight
                            ? "bg-[#f97316] hover:bg-[#ea6c0a] text-white"
                            : "bg-[#1e3a5f] hover:bg-[#162d4a] text-white"
                        }`}
                      >
                        {plan.cta}
                      </Button>
                    </Link>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
          <p className="text-center text-sm text-slate-400 mt-6">
            <Link href="/pricing" className="text-[#1e3a5f] underline underline-offset-4">
              See full pricing details →
            </Link>
          </p>
        </div>
      </section>

      {/* ── FINAL CTA ── */}
      <section className="py-20 bg-[#1e3a5f]">
        <div className="mx-auto max-w-3xl px-4 text-center">
          <h2 className="text-3xl font-extrabold text-white mb-3">
            Ready to plan your first project?
          </h2>
          <p className="text-slate-300 text-lg mb-8">Sign up free — no credit card required.</p>
          <Link href="/sign-up">
            <Button
              size="lg"
              className="bg-[#f97316] hover:bg-[#ea6c0a] text-white font-bold px-10"
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
