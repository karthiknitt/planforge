import {
  ArrowRight,
  Building2,
  CheckCircle,
  FileText,
  LayoutGrid,
  MapPin,
  Package,
  Ruler,
  ShieldCheck,
  Sparkles,
  Zap,
} from "lucide-react";
import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";
import { AnimatedFloorPlan } from "@/components/animated-floor-plan";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { auth } from "@/lib/auth";

/* ──────────────────────────────────────────────────────────────
   Bento features — 2 large + 4 small for visual hierarchy
────────────────────────────────────────────────────────────── */
const bentoPrimary = [
  {
    icon: ShieldCheck,
    title: "NBC 2016 Compliance",
    desc: "Automatic setback, FAR, and room-size checks for Bangalore, Chennai, Delhi, Hyderabad, and Pune. Every layout is validated before you export.",
    accent: "from-emerald-500/10 to-emerald-500/5",
    iconBg: "bg-emerald-500/10 ring-emerald-500/20",
    iconColor: "text-emerald-400",
  },
  {
    icon: LayoutGrid,
    title: "5 Layout Variations",
    desc: "Front, centre, rear, corner, and open-plan archetypes generated instantly. Compare side-by-side, pick the best fit for your client.",
    accent: "from-blue-500/10 to-blue-500/5",
    iconBg: "bg-blue-500/10 ring-blue-500/20",
    iconColor: "text-blue-400",
  },
];

const bentoSecondary = [
  {
    icon: FileText,
    title: "CAD-Grade Export",
    desc: "PDF at 1:100 scale with dimensions, north arrow, title block. DXF with 9 named layers.",
  },
  {
    icon: Package,
    title: "Bill of Quantities",
    desc: "Auto-calculated masonry, concrete, steel, and flooring. Export to Excel.",
  },
  {
    icon: Building2,
    title: "1\u20134 BHK Support",
    desc: "Compact 1BHK to spacious 4BHK. Optional pooja room, study, balcony.",
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
    desc: "Dimensions, city, setbacks, road direction, BHK count, optional rooms.",
    icon: Ruler,
  },
  {
    num: "02",
    title: "Get 5 Layouts",
    desc: "Engine generates all archetypes and checks each against NBC + city rules.",
    icon: Zap,
  },
  {
    num: "03",
    title: "Export & Build",
    desc: "Download PDF, DXF for AutoCAD, or BOQ Excel \u2014 all from a single click.",
    icon: FileText,
  },
];

/* ──────────────────────────────────────────────────────────────
   Trust metrics
────────────────────────────────────────────────────────────── */
const metrics = [
  { value: "5", label: "Layout variations" },
  { value: "6", label: "Cities supported" },
  { value: "9", label: "DXF CAD layers" },
  { value: "11", label: "BOQ line items" },
];

/* ──────────────────────────────────────────────────────────────
   Pricing
────────────────────────────────────────────────────────────── */
const plans = [
  {
    name: "Free",
    price: "\u20B90",
    period: "/month",
    perks: ["3 projects", "PDF export", "All 5 layouts"],
    cta: "Get Started",
    highlight: false,
  },
  {
    name: "Basic",
    price: "\u20B9499",
    period: "/month",
    perks: ["Unlimited projects", "PDF + DXF export", "All 5 layouts"],
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
    "Input plot dimensions, get 5 NBC-compliant layout variations instantly \u2014 PDF, DXF, BOQ export.",
  openGraph: {
    title: "PlanForge \u2014 G+1 Floor Plan Generator",
    description:
      "Input plot dimensions, get 5 NBC-compliant layout variations instantly \u2014 PDF, DXF, BOQ export.",
  },
};

export default async function LandingPage() {
  const session = await auth.api.getSession({ headers: await headers() });
  if (session) redirect("/dashboard");

  return (
    <>
      {/* ── HERO ── */}
      <section className="relative overflow-hidden bg-background min-h-[90vh] flex items-center">
        <div className="absolute inset-0 bg-blueprint-grid opacity-100" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_10%_50%,rgba(249,115,22,0.08)_0%,transparent_50%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_90%_20%,rgba(96,165,250,0.06)_0%,transparent_45%)]" />
        <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-background to-transparent" />

        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-20 lg:py-28 w-full">
          <div className="grid lg:grid-cols-2 gap-16 lg:gap-20 items-center">
            {/* Left: copy */}
            <div>
              <div className="animate-fade-up delay-100">
                <Badge className="mb-6 bg-primary/10 text-primary border-primary/25 hover:bg-primary/15 text-xs tracking-wide">
                  <Sparkles className="h-3 w-3 mr-1.5" />
                  NBC 2016 Compliant
                </Badge>
              </div>
              <h1
                className="animate-fade-up delay-200 text-4xl sm:text-5xl lg:text-[3.5rem] font-black tracking-tight text-foreground leading-[1.08] mb-6"
                style={{ fontFamily: "var(--font-display)" }}
              >
                Generate G+1
                <br />
                Floor Plans
                <br />
                <span className="text-gradient-orange">in Seconds</span>
              </h1>
              <p className="animate-fade-up delay-300 text-base sm:text-lg text-muted-foreground mb-10 leading-relaxed max-w-lg">
                Input your plot dimensions, get 5 layout variations instantly &mdash; each
                NBC-compliant, export-ready as PDF or DXF. Built for Indian civil engineers and small
                builders.
              </p>
              <div className="animate-fade-up delay-400 flex flex-wrap gap-4">
                <Link href="/sign-up">
                  <Button
                    size="lg"
                    className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-8 h-12 btn-shine shadow-lg shadow-primary/20"
                  >
                    Start Free
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                </Link>
                <Link href="/how-it-works">
                  <Button
                    size="lg"
                    variant="outline"
                    className="border-border/80 text-foreground hover:bg-muted font-semibold px-8 h-12"
                  >
                    See How It Works
                  </Button>
                </Link>
              </div>
              <p className="animate-fade-up delay-500 mt-5 text-sm text-muted-foreground/70">
                No credit card required &mdash; Free forever plan available
              </p>
            </div>

            {/* Right: floor plan preview */}
            <div className="animate-scale-in delay-300 relative hidden sm:block">
              <div className="rounded-2xl border border-border/40 shadow-2xl shadow-black/30 overflow-hidden bg-card/80 backdrop-blur-sm">
                <div className="px-4 pt-3.5 pb-2.5 border-b border-border/30 bg-muted/20 flex items-center gap-2">
                  <div className="flex gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-full bg-red-500/60" />
                    <span className="h-2.5 w-2.5 rounded-full bg-yellow-500/60" />
                    <span className="h-2.5 w-2.5 rounded-full bg-green-500/60" />
                  </div>
                  <span
                    className="text-[11px] font-medium text-muted-foreground/70 ml-1"
                    style={{ fontFamily: "var(--font-mono)" }}
                  >
                    Layout A &middot; Front Staircase &middot; 2BHK
                  </span>
                </div>
                <div className="p-4">
                  <AnimatedFloorPlan />
                </div>
              </div>
              <div className="absolute -top-3 -right-3 bg-primary text-primary-foreground text-xs font-bold px-3.5 py-1.5 rounded-full shadow-lg shadow-primary/30 animate-float animate-pulse-ring">
                5 layouts
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── TRUST METRICS STRIP ── */}
      <section className="relative border-y border-border/30 bg-card/30">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-4 divide-x divide-border/30">
            {metrics.map(({ value, label }) => (
              <div key={label} className="px-6 py-8 text-center">
                <div
                  className="text-3xl sm:text-4xl font-black text-primary stat-value mb-1"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  {value}
                </div>
                <div className="text-xs sm:text-sm text-muted-foreground font-medium">{label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FEATURES — BENTO GRID ── */}
      <section className="py-24 lg:py-32 bg-background relative">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_0%,rgba(249,115,22,0.04)_0%,transparent_60%)]" />
        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="animate-fade-up text-center mb-16">
            <p className="text-xs font-bold text-primary uppercase tracking-[0.2em] mb-3">
              Features
            </p>
            <h2
              className="text-3xl lg:text-4xl font-black text-foreground mb-4"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Everything you need to design & deliver
            </h2>
            <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
              From compliance checks to CAD-ready exports &mdash; in one tool.
            </p>
          </div>

          {/* Primary — 2 large cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-5">
            {bentoPrimary.map(({ icon: Icon, title, desc, accent, iconBg, iconColor }, i) => (
              <div
                key={title}
                className={`animate-fade-up bento-card rounded-2xl border border-border/60 bg-gradient-to-br ${accent} p-8 backdrop-blur-sm`}
                style={{ animationDelay: `${200 + i * 100}ms` }}
              >
                <div
                  className={`flex h-12 w-12 items-center justify-center rounded-xl ${iconBg} ring-1 mb-5`}
                >
                  <Icon className={`h-6 w-6 ${iconColor}`} />
                </div>
                <h3
                  className="text-xl font-bold text-foreground mb-3"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  {title}
                </h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>

          {/* Secondary — 4 smaller cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {bentoSecondary.map(({ icon: Icon, title, desc }, i) => (
              <div
                key={title}
                className="animate-fade-up feature-card rounded-2xl border border-border/60 bg-card/50 backdrop-blur-sm p-6"
                style={{ animationDelay: `${400 + i * 100}ms` }}
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 ring-1 ring-primary/20 mb-4">
                  <Icon className="h-5 w-5 text-primary" />
                </div>
                <h3
                  className="text-sm font-bold text-foreground mb-2"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  {title}
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section className="py-24 lg:py-32 bg-card/20 border-y border-border/30">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="animate-fade-up text-center mb-16">
            <p className="text-xs font-bold text-primary uppercase tracking-[0.2em] mb-3">
              How It Works
            </p>
            <h2
              className="text-3xl lg:text-4xl font-black text-foreground mb-4"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Three steps from plot to plan
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 lg:gap-10">
            {steps.map((step, i) => {
              const Icon = step.icon;
              return (
                <div
                  key={step.num}
                  className="animate-fade-up relative flex flex-col items-center text-center group"
                  style={{ animationDelay: `${200 + i * 150}ms` }}
                >
                  {/* Connector line */}
                  {i < steps.length - 1 && (
                    <div className="hidden md:block absolute top-7 left-[calc(50%+2rem)] w-[calc(100%-4rem)] h-[2px] bg-gradient-to-r from-primary/30 to-primary/5" />
                  )}
                  {/* Step number circle */}
                  <div className="relative z-10 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary text-primary-foreground font-black text-lg mb-6 shadow-lg shadow-primary/20 group-hover:shadow-primary/40 transition-shadow">
                    {step.num}
                  </div>
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-muted/50 ring-1 ring-border/50 mb-4">
                    <Icon className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <h3
                    className="text-lg font-bold text-foreground mb-2"
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    {step.title}
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed max-w-xs">
                    {step.desc}
                  </p>
                </div>
              );
            })}
          </div>
          <div className="mt-12 text-center">
            <Link href="/how-it-works">
              <Button variant="outline" className="border-border/60 text-foreground hover:bg-muted">
                Full walkthrough
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* ── PRICING PREVIEW ── */}
      <section className="py-24 lg:py-32 bg-background relative">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_100%,rgba(249,115,22,0.04)_0%,transparent_60%)]" />
        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="animate-fade-up text-center mb-16">
            <p className="text-xs font-bold text-primary uppercase tracking-[0.2em] mb-3">
              Pricing
            </p>
            <h2
              className="text-3xl lg:text-4xl font-black text-foreground mb-4"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Simple, Transparent Pricing
            </h2>
            <p className="text-muted-foreground text-lg">Start free. Upgrade when you need more.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5 lg:gap-6 max-w-4xl mx-auto">
            {plans.map((plan, i) => (
              <div
                key={plan.name}
                className={`animate-fade-up relative flex flex-col rounded-2xl border p-7 backdrop-blur-sm transition-all ${
                  plan.highlight
                    ? "glow-card border-primary/40 bg-card"
                    : "border-border/50 bg-card/50 hover:border-border"
                }`}
                style={{ animationDelay: `${200 + i * 100}ms` }}
              >
                {plan.highlight && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-primary text-primary-foreground text-[10px] font-bold px-4 py-1 rounded-full shadow-lg shadow-primary/25 uppercase tracking-wider">
                    Most Popular
                  </div>
                )}
                <div className="mb-5">
                  <p className="text-[10px] font-bold text-muted-foreground/60 uppercase tracking-[0.2em] mb-2">
                    {plan.name}
                  </p>
                  <div className="flex items-baseline gap-1">
                    <span
                      className="text-4xl font-black text-foreground"
                      style={{ fontFamily: "var(--font-display)" }}
                    >
                      {plan.price}
                    </span>
                    <span className="text-muted-foreground/70 text-sm">{plan.period}</span>
                  </div>
                </div>
                <ul className="space-y-3 flex-1 mb-7">
                  {plan.perks.map((p) => (
                    <li key={p} className="flex items-center gap-2.5 text-sm text-muted-foreground">
                      <CheckCircle className="h-3.5 w-3.5 text-primary flex-shrink-0" />
                      {p}
                    </li>
                  ))}
                </ul>
                <Link href="/sign-up" className="block">
                  <Button
                    className={`w-full font-bold ${
                      plan.highlight
                        ? "bg-primary hover:bg-primary/90 text-primary-foreground btn-shine shadow-md shadow-primary/20"
                        : "bg-transparent hover:bg-muted text-foreground border border-border/60"
                    }`}
                  >
                    {plan.cta}
                  </Button>
                </Link>
              </div>
            ))}
          </div>
          <p className="text-center text-sm text-muted-foreground/60 mt-8">
            <Link href="/pricing" className="text-primary hover:underline underline-offset-4">
              See full pricing details &rarr;
            </Link>
          </p>
        </div>
      </section>

      {/* ── FINAL CTA ── */}
      <section className="py-24 lg:py-32 relative overflow-hidden bg-gradient-to-br from-primary/[0.06] via-background to-background border-t border-border/30">
        <div className="absolute inset-0 bg-blueprint-grid opacity-40" />
        <div className="animate-fade-up relative mx-auto max-w-3xl px-4 text-center">
          <h2
            className="text-3xl lg:text-4xl font-black text-foreground mb-4"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Ready to plan your first project?
          </h2>
          <p className="text-muted-foreground text-lg mb-10">
            Sign up free &mdash; no credit card required.
          </p>
          <Link href="/sign-up">
            <Button
              size="lg"
              className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-10 h-12 btn-shine shadow-lg shadow-primary/20"
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
