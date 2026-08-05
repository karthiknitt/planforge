import {
  ArrowRight,
  Building2,
  CheckCircle,
  FileText,
  LayoutGrid,
  MapPin,
  Package,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { JsonLd } from "@/components/json-ld";
import { FadeIn } from "@/components/motion/fade-in";
import { StaggerChildren, StaggerItem } from "@/components/motion/stagger-children";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  ARCHETYPE_COUNT,
  getFaqsForPage,
  howItWorksSteps,
  pricingTiers,
} from "@/lib/marketing-content";

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
    title: `${ARCHETYPE_COUNT} Layout Variations`,
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
   Steps, pricing tiers, and FAQ now come from the single-source
   marketing content module (lib/marketing-content.ts) shared with
   the pricing and how-it-works pages — see that file for the
   canonical data. Landing shows all of howItWorksSteps rather than
   an invented shorter subset.
────────────────────────────────────────────────────────────── */
const faqs = getFaqsForPage("landing");

/* ──────────────────────────────────────────────────────────────
   Social proof stats
────────────────────────────────────────────────────────────── */
const stats = [
  { value: String(ARCHETYPE_COUNT), label: "Layout archetypes" },
  { value: "6+", label: "Indian cities" },
  { value: "NBC", label: "2016 compliant" },
  { value: "Minutes", label: "Generation time" },
];

/* ──────────────────────────────────────────────────────────────
   Page
────────────────────────────────────────────────────────────── */
export const metadata: Metadata = {
  // The root layout applies `template: "%s | PlanForge"`, so do NOT repeat the suffix here.
  title: "G+1 Floor Plan Generator for Indian Builders — NBC 2016 Compliant",
  description:
    "Generate 5 NBC 2016-compliant G+1 floor plan variations in minutes. Enter plot dimensions, get PDF, DXF & BOQ export. Free plan available. No AutoCAD needed.",
  keywords: [
    "G+1 floor plan generator",
    "floor plan generator India",
    "NBC 2016 compliant floor plan",
    "residential floor plan India",
    "2BHK 3BHK floor plan",
    "house plan Bangalore Chennai Delhi",
    "free floor plan generator",
    "DXF floor plan AutoCAD",
  ],
  openGraph: {
    title: "PlanForge — Generate G+1 Floor Plans in Minutes",
    description:
      "5 NBC-compliant layout variations from your plot dimensions. PDF, DXF & BOQ export. Free to start. Built for Indian civil engineers.",
  },
  alternates: { canonical: "/" },
};

export default function LandingPage() {
  const softwareJsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "PlanForge",
    applicationCategory: "DesignApplication",
    operatingSystem: "Web",
    url: "https://planforge.in",
    description:
      "G+1 residential floor plan generator for Indian builders. NBC 2016 compliant. 5 layout variations, PDF & DXF export.",
    screenshot: "https://planforge.in/opengraph-image",
    featureList: [
      "NBC 2016 compliance checks",
      `${ARCHETYPE_COUNT} layout archetypes (front, centre, rear, corner, open-plan)`,
      "PDF export at 1:100 scale",
      "DXF export with 9 named layers",
      "BOQ Excel with 11 quantity items",
      "City-specific rules for Bangalore, Chennai, Delhi, Hyderabad, Pune",
    ],
    offers: pricingTiers.map((tier) => ({
      "@type": "Offer",
      price: tier.price.replace(/[₹,]/g, "") || "0",
      priceCurrency: "INR",
      name: tier.name,
    })),
    author: { "@type": "Organization", name: "PlanForge", url: "https://planforge.in" },
  };

  const faqJsonLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map(({ q, a }) => ({
      "@type": "Question",
      name: q,
      acceptedAnswer: { "@type": "Answer", text: a },
    })),
  };

  return (
    <>
      <JsonLd data={softwareJsonLd} />
      <JsonLd data={faqJsonLd} />
      {/* ── HERO ── */}
      <section className="relative overflow-hidden bg-background border-b border-border/50 min-h-[90vh] flex items-center">
        {/* Blueprint grid overlay */}
        <div className="absolute inset-0 bg-blueprint-grid opacity-100" />
        {/* Radial glows */}
        <div className="absolute inset-0 ambient-glow-orange-tl" />
        <div className="absolute inset-0 ambient-glow-orange-tr" />
        <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-background to-transparent" />

        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-20 lg:py-28 w-full">
          <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
            {/* Left: copy */}
            <div>
              <div className="animate-fade-up delay-100">
                <Badge className="mb-6 bg-primary/10 text-primary border-primary/30 hover:bg-primary/15 px-4 py-1.5">
                  <Sparkles className="h-3 w-3 mr-1.5" />
                  NBC 2016 Compliant · AI-Powered
                </Badge>
              </div>
              <h1
                className="text-5xl sm:text-6xl lg:text-7xl font-black tracking-tight text-foreground leading-[1.05] mb-6"
                style={{ fontFamily: "var(--font-display)" }}
              >
                Generate G+1
                <br />
                Floor Plans
                <br />
                <span className="text-gradient-orange">in Minutes</span>
              </h1>
              <p className="animate-fade-up delay-300 text-lg md:text-xl text-muted-foreground mb-10 leading-relaxed max-w-lg">
                Input your plot dimensions, get {ARCHETYPE_COUNT} layout variations instantly — each
                NBC-compliant, export-ready as PDF or DXF. Built for Indian civil engineers and
                small builders.
              </p>
              <div className="animate-fade-up delay-400 flex flex-wrap gap-3 mb-6">
                <Link href="/sign-up">
                  <Button
                    size="lg"
                    className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-8 h-12 btn-shine shadow-xl shadow-primary/25 text-base"
                  >
                    Start Free
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                </Link>
                <Link href="/how-it-works">
                  <Button
                    size="lg"
                    variant="outline"
                    className="border-border/80 text-foreground hover:bg-muted font-semibold px-8 h-12 text-base"
                  >
                    See How It Works
                  </Button>
                </Link>
              </div>
              <p className="animate-fade-up delay-500 text-sm text-muted-foreground">
                No credit card required &nbsp;·&nbsp; Free forever plan available
              </p>
            </div>

            {/* Right: floor plan preview */}
            <div className="relative">
              <div className="rounded-2xl border border-border/60 shadow-2xl shadow-black/50 overflow-hidden bg-card">
                <div className="px-4 pt-3 pb-2 border-b border-border/50 bg-muted/30 flex items-center gap-2">
                  <div className="flex gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-full bg-red-500/70" />
                    <span className="h-2.5 w-2.5 rounded-full bg-yellow-500/70" />
                    <span className="h-2.5 w-2.5 rounded-full bg-green-500/70" />
                  </div>
                  <span
                    className="text-xs font-medium text-muted-foreground ml-1"
                    style={{ fontFamily: "var(--font-mono)" }}
                  >
                    Layout A · Front Staircase · 2BHK · Bangalore
                  </span>
                </div>
                <Image
                  src="/hero-illustration.png"
                  alt="NBC-compliant G+1 floor plan with colour-coded rooms, dimension lines and north arrow"
                  width={1200}
                  height={630}
                  className="w-full h-auto"
                  priority
                />
              </div>
              <div className="absolute -top-3 -right-3 bg-primary text-primary-foreground text-xs font-bold px-3 py-1.5 rounded-full shadow-lg shadow-primary/30 animate-float">
                {ARCHETYPE_COUNT} layouts
              </div>
              {/* Decorative glow behind the card */}
              <div className="absolute -inset-4 bg-primary/5 rounded-3xl blur-2xl -z-10" />
            </div>
          </div>

          {/* Stats row */}
          <FadeIn delay={0.5} className="mt-16 lg:mt-20">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-6 lg:gap-8 border border-border/50 rounded-2xl bg-card/50 backdrop-blur-sm p-6 lg:p-8">
              {stats.map(({ value, label }) => (
                <div key={label} className="text-center">
                  <div
                    className="text-3xl lg:text-4xl font-black text-primary mb-1"
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    {value}
                  </div>
                  <div className="text-sm text-muted-foreground">{label}</div>
                </div>
              ))}
            </div>
          </FadeIn>
        </div>
      </section>

      {/* ── FEATURES ── */}
      <section className="py-24 lg:py-32 bg-background relative">
        <div className="absolute inset-0 ambient-glow-orange-top" />
        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <FadeIn className="text-center mb-16">
            <Badge className="mb-4 bg-primary/10 text-primary border-primary/25 hover:bg-primary/15">
              Features
            </Badge>
            <h2
              className="text-3xl md:text-4xl lg:text-5xl font-bold text-foreground mb-4"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Everything you need to design &amp; deliver
            </h2>
            <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
              From compliance checks to CAD-ready exports — in one tool.
            </p>
          </FadeIn>
          <StaggerChildren className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
            {features.map(({ icon: Icon, title, desc }) => (
              <StaggerItem key={title}>
                <div className="feature-card group rounded-2xl border border-border/60 bg-card p-6 h-full hover:border-primary/25 transition-all duration-300">
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 ring-1 ring-primary/20 mb-5 group-hover:bg-primary/15 group-hover:ring-primary/30 transition-colors">
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
              </StaggerItem>
            ))}
          </StaggerChildren>
        </div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section className="py-24 lg:py-32 bg-muted/20 border-y border-border/50">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <FadeIn className="text-center mb-16">
            <Badge className="mb-4 bg-primary/10 text-primary border-primary/25 hover:bg-primary/15">
              How It Works
            </Badge>
            <h2
              className="text-3xl md:text-4xl lg:text-5xl font-bold text-foreground mb-4"
              style={{ fontFamily: "var(--font-display)" }}
            >
              {howItWorksSteps.length} steps from plot to plan
            </h2>
            <p className="text-muted-foreground text-lg">Simple. Fast. Built for builders.</p>
          </FadeIn>
          <StaggerChildren className="grid md:grid-cols-2 lg:grid-cols-4 gap-8 lg:gap-10">
            {howItWorksSteps.map((step, i) => (
              <StaggerItem key={step.num}>
                <div className="relative flex flex-col items-center text-center">
                  {i < howItWorksSteps.length - 1 && (
                    <div className="hidden lg:block absolute top-6 left-[calc(50%+2.5rem)] w-[calc(100%-5rem)] h-px bg-gradient-to-r from-primary/40 to-primary/10" />
                  )}
                  <div className="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-primary to-amber-600 text-primary-foreground font-extrabold text-lg mb-5 z-10 shadow-xl shadow-primary/25">
                    {step.num}
                  </div>
                  <h3
                    className="text-xl font-bold text-foreground mb-3"
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    {step.title}
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">{step.text}</p>
                </div>
              </StaggerItem>
            ))}
          </StaggerChildren>
          <div className="mt-12 text-center">
            <Link href="/how-it-works">
              <Button
                variant="outline"
                size="lg"
                className="border-border/80 text-foreground hover:bg-muted font-semibold px-8"
              >
                Full walkthrough
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* ── PRICING PREVIEW ── */}
      <section className="py-24 lg:py-32 bg-background relative">
        <div className="absolute inset-0 ambient-glow-orange-bottom" />
        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <FadeIn className="text-center mb-16">
            <Badge className="mb-4 bg-primary/10 text-primary border-primary/25 hover:bg-primary/15">
              Pricing
            </Badge>
            <h2
              className="text-3xl md:text-4xl lg:text-5xl font-bold text-foreground mb-4"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Simple, transparent pricing
            </h2>
            <p className="text-muted-foreground text-lg">Start free. Upgrade when you need more.</p>
          </FadeIn>
          <StaggerChildren className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 max-w-6xl mx-auto">
            {pricingTiers.map((plan) => (
              <StaggerItem key={plan.id}>
                <div
                  className={`relative flex flex-col rounded-2xl border p-7 h-full transition-all ${
                    plan.highlight
                      ? "glow-card border-primary/60 bg-card scale-[1.03]"
                      : "border-border/60 bg-card hover:border-border"
                  }`}
                >
                  {plan.highlight && (
                    <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 bg-gradient-to-r from-primary to-amber-500 text-primary-foreground text-xs font-bold px-4 py-1.5 rounded-full shadow-lg shadow-primary/30">
                      Most Popular
                    </div>
                  )}
                  <div className="mb-2">
                    <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-1">
                      {plan.name}
                    </p>
                    <p className="text-sm text-muted-foreground mb-4">{plan.tagline}</p>
                    <div className="flex items-baseline gap-1 mb-6">
                      <span
                        className="text-4xl font-black text-foreground"
                        style={{ fontFamily: "var(--font-display)" }}
                      >
                        {plan.price}
                      </span>
                      <span className="text-muted-foreground text-sm">{plan.period}</span>
                    </div>
                  </div>
                  <ul className="space-y-3 flex-1 mb-7">
                    {plan.perks.map((p) => (
                      <li key={p} className="flex items-center gap-2.5 text-sm">
                        <CheckCircle className="h-4 w-4 text-primary flex-shrink-0" />
                        <span className="text-foreground/85">{p}</span>
                      </li>
                    ))}
                  </ul>
                  <Link href="/sign-up">
                    <Button
                      className={`w-full font-bold h-11 ${
                        plan.highlight
                          ? "bg-primary hover:bg-primary/90 text-primary-foreground btn-shine shadow-md shadow-primary/20"
                          : "bg-transparent hover:bg-muted text-foreground border border-border"
                      }`}
                    >
                      {plan.cta}
                    </Button>
                  </Link>
                </div>
              </StaggerItem>
            ))}
          </StaggerChildren>
          <p className="text-center text-sm text-muted-foreground mt-8">
            <Link href="/pricing" className="text-primary hover:underline underline-offset-4">
              See full pricing details &rarr;
            </Link>
          </p>
        </div>
      </section>

      {/* ── FAQ ── */}
      <section className="py-24 lg:py-32 bg-muted/20 border-y border-border/50">
        <div className="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8">
          <FadeIn className="text-center mb-12">
            <Badge className="mb-4 bg-primary/10 text-primary border-primary/25 hover:bg-primary/15">
              FAQ
            </Badge>
            <h2
              className="text-3xl md:text-4xl font-bold text-foreground"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Frequently asked questions
            </h2>
          </FadeIn>
          <StaggerChildren className="space-y-3">
            <Accordion type="single" collapsible className="space-y-3">
              {faqs.map(({ q, a }) => (
                <StaggerItem key={q}>
                  <AccordionItem
                    value={q}
                    className="border border-border/60 bg-card rounded-xl px-5"
                  >
                    <AccordionTrigger className="text-sm font-semibold text-foreground hover:no-underline">
                      {q}
                    </AccordionTrigger>
                    <AccordionContent className="text-sm text-muted-foreground leading-relaxed">
                      {a}
                    </AccordionContent>
                  </AccordionItem>
                </StaggerItem>
              ))}
            </Accordion>
          </StaggerChildren>
        </div>
      </section>

      {/* ── FINAL CTA ── */}
      <section className="py-24 lg:py-32 relative overflow-hidden bg-gradient-to-br from-primary/10 via-background to-background border-t border-border/50">
        <div className="absolute inset-0 bg-blueprint-grid opacity-40" />
        <div className="absolute inset-0 ambient-glow-orange" />
        <FadeIn className="relative mx-auto max-w-3xl px-4 text-center">
          <Badge className="mb-6 bg-primary/10 text-primary border-primary/25 hover:bg-primary/15">
            Get Started Today
          </Badge>
          <h2
            className="text-3xl md:text-4xl lg:text-5xl font-black text-foreground mb-4"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Ready to plan your first project?
          </h2>
          <p className="text-muted-foreground text-lg mb-10">
            Sign up free — no credit card required. Start generating NBC-compliant floor plans in
            minutes.
          </p>
          <div className="flex flex-wrap justify-center gap-4">
            <Link href="/sign-up">
              <Button
                size="lg"
                className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-10 h-12 btn-shine shadow-xl shadow-primary/25 text-base"
              >
                Start Free
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
            <Link href="/pricing">
              <Button
                size="lg"
                variant="outline"
                className="border-border/80 text-foreground hover:bg-muted font-semibold px-8 h-12 text-base"
              >
                View Pricing
              </Button>
            </Link>
          </div>
        </FadeIn>
      </section>
    </>
  );
}
