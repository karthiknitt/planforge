import { FadeIn } from "@/components/motion/fade-in";
import { StaggerChildren, StaggerItem } from "@/components/motion/stagger-children";
import { PricingCheckoutButton } from "@/components/pricing-checkout-button";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CheckCircle, X } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Pricing — PlanForge",
  description: "Simple, transparent pricing for PlanForge floor plan generator.",
};

const plans: Array<{
  name: string;
  price: string;
  period: string;
  tagline: string;
  highlight: boolean;
  cta: string;
  checkoutPlan: "basic" | "pro" | null;
  features: Array<{ text: string; included: boolean }>;
}> = [
  {
    name: "Free",
    price: "₹0",
    period: "/month",
    tagline: "Try it out, no commitment.",
    highlight: false,
    cta: "Get Started Free",
    checkoutPlan: null,
    features: [
      { text: "3 saved projects", included: true },
      { text: "All 5 layout archetypes", included: true },
      { text: "NBC 2016 compliance checks", included: true },
      { text: "PDF export (1:100 scale)", included: true },
      { text: "DXF export for AutoCAD", included: false },
      { text: "BOQ Excel export", included: false },
      { text: "Priority support", included: false },
    ],
  },
  {
    name: "Basic",
    price: "₹499",
    period: "/month",
    tagline: "For active builders and designers.",
    highlight: true,
    cta: "Subscribe — ₹499/mo",
    checkoutPlan: "basic",
    features: [
      { text: "Unlimited saved projects", included: true },
      { text: "All 5 layout archetypes", included: true },
      { text: "NBC 2016 compliance checks", included: true },
      { text: "PDF export (1:100 scale)", included: true },
      { text: "DXF export for AutoCAD", included: true },
      { text: "BOQ Excel export", included: false },
      { text: "Priority support", included: false },
    ],
  },
  {
    name: "Pro",
    price: "₹999",
    period: "/month",
    tagline: "For professionals delivering to clients.",
    highlight: false,
    cta: "Subscribe — ₹999/mo",
    checkoutPlan: "pro",
    features: [
      { text: "Unlimited saved projects", included: true },
      { text: "All 5 layout archetypes", included: true },
      { text: "NBC 2016 compliance checks", included: true },
      { text: "PDF export (1:100 scale)", included: true },
      { text: "DXF export for AutoCAD", included: true },
      { text: "BOQ Excel export", included: true },
      { text: "Priority support", included: true },
    ],
  },
];

const faqs = [
  {
    q: "Do I need AutoCAD to use PlanForge?",
    a: "No. PlanForge runs entirely in your browser — no software to install. DXF export is available for Basic and Pro subscribers who want to open plans in AutoCAD, BricsCAD, or any other CAD tool.",
  },
  {
    q: "Which cities are supported?",
    a: "Bangalore, Chennai, Delhi, Hyderabad, Pune, and a generic Indian standard option that applies NBC 2016 defaults. City-specific setbacks and FAR tables are baked in for each supported city.",
  },
  {
    q: "What compliance standards are used?",
    a: "PlanForge enforces NBC 2016 for room areas, minimum widths, stair tread/riser dimensions, and ventilation ratios. City-specific setbacks and floor area ratios (FAR) are applied on top of the national baseline.",
  },
  {
    q: "Can I cancel anytime?",
    a: "Yes. You can cancel your subscription at any time from your account settings. Your access continues until the end of the current billing period, and you won't be charged again.",
  },
  {
    q: "What is a BOQ?",
    a: "A Bill of Quantities (BOQ) is a breakdown of construction materials with estimated quantities — masonry, concrete, structural steel, plaster, flooring, and more. PlanForge auto-calculates 11 quantity line items and lets you export them to Excel for cost estimation.",
  },
];

export default function PricingPage() {
  return (
    <div className="bg-background">
      {/* Header */}
      <section className="py-20 lg:py-28 bg-gradient-to-b from-muted/40 to-background border-b border-border/50 relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_0%,rgba(249,115,22,0.07)_0%,transparent_60%)]" />
        <FadeIn className="relative mx-auto max-w-4xl px-4 text-center">
          <Badge className="mb-5 bg-primary/10 text-primary border-primary/25 hover:bg-primary/15 px-4 py-1.5">
            Transparent pricing
          </Badge>
          <h1
            className="text-4xl md:text-5xl lg:text-6xl font-extrabold text-foreground mb-4"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Simple, Transparent Pricing
          </h1>
          <p className="text-lg md:text-xl text-muted-foreground">
            Start free. Upgrade when you need more.
          </p>
        </FadeIn>
      </section>

      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Pricing cards */}
        <StaggerChildren className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto py-16 lg:py-20">
          {plans.map((plan) => (
            <StaggerItem key={plan.name}>
              <div
                className={`relative flex flex-col rounded-2xl border h-full transition-all ${
                  plan.highlight
                    ? "border-primary/60 bg-card shadow-2xl shadow-primary/10 scale-[1.03]"
                    : "border-border/60 bg-card/80 shadow-sm hover:border-border hover:shadow-md"
                }`}
              >
                {plan.highlight && (
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2 bg-gradient-to-r from-primary to-amber-500 text-primary-foreground text-xs font-bold px-5 py-1.5 rounded-full shadow-lg shadow-primary/30">
                    Most Popular
                  </div>
                )}
                {/* Card header */}
                <div
                  className={`px-7 pt-8 pb-6 rounded-t-2xl ${plan.highlight ? "bg-primary/5" : ""}`}
                >
                  <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-1">
                    {plan.name}
                  </p>
                  <div className="flex items-baseline gap-1 mb-1">
                    <span
                      className="text-5xl font-extrabold text-foreground"
                      style={{ fontFamily: "var(--font-display)" }}
                    >
                      {plan.price}
                    </span>
                    <span className="text-muted-foreground text-sm">{plan.period}</span>
                  </div>
                  <p className="text-sm text-muted-foreground mt-1">{plan.tagline}</p>
                </div>

                <div className="px-7 pb-7 flex-1 flex flex-col gap-6">
                  {/* Divider */}
                  <div className="h-px bg-border/60" />
                  {/* Feature list */}
                  <ul className="space-y-3 flex-1">
                    {plan.features.map((f) => (
                      <li key={f.text} className="flex items-start gap-3">
                        {f.included ? (
                          <CheckCircle className="h-4 w-4 text-primary flex-shrink-0 mt-0.5" />
                        ) : (
                          <X className="h-4 w-4 text-muted-foreground/40 flex-shrink-0 mt-0.5" />
                        )}
                        <span
                          className={`text-sm ${
                            f.included ? "text-foreground/85" : "text-muted-foreground/50"
                          }`}
                        >
                          {f.text}
                        </span>
                      </li>
                    ))}
                  </ul>

                  {/* CTA */}
                  <div className="mt-auto">
                    {plan.checkoutPlan ? (
                      <PricingCheckoutButton
                        plan={plan.checkoutPlan}
                        label={plan.cta}
                        highlight={plan.highlight}
                      />
                    ) : (
                      <Link href="/sign-up" className="block">
                        <Button
                          variant="outline"
                          className="w-full font-bold h-11 border-border text-foreground hover:bg-muted"
                        >
                          {plan.cta}
                        </Button>
                      </Link>
                    )}
                  </div>
                </div>
              </div>
            </StaggerItem>
          ))}
        </StaggerChildren>

        {/* FAQ */}
        <div className="max-w-3xl mx-auto pb-20">
          <FadeIn>
            <h2
              className="text-2xl md:text-3xl font-extrabold text-foreground mb-10 text-center"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Frequently Asked Questions
            </h2>
          </FadeIn>
          <Accordion type="single" collapsible className="space-y-2">
            {faqs.map((faq) => (
              <AccordionItem
                key={faq.q}
                value={faq.q}
                className="border border-border/60 bg-card rounded-xl px-5 shadow-sm"
              >
                <AccordionTrigger className="text-left text-sm font-semibold text-foreground hover:no-underline py-4">
                  {faq.q}
                </AccordionTrigger>
                <AccordionContent className="text-sm text-muted-foreground leading-relaxed pb-5">
                  {faq.a}
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </div>
      </div>

      {/* Bottom CTA */}
      <section className="py-20 lg:py-24 relative overflow-hidden bg-gradient-to-br from-primary/10 via-muted/20 to-background border-t border-border/50">
        <div className="absolute inset-0 bg-blueprint-grid opacity-30" />
        <FadeIn className="relative text-center px-4">
          <h2
            className="text-2xl md:text-3xl font-extrabold text-foreground mb-3"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Still have questions?
          </h2>
          <p className="text-muted-foreground mb-8 text-lg">
            Start for free — no credit card required.
          </p>
          <Link href="/sign-up">
            <Button
              size="lg"
              className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-10 h-12 btn-shine shadow-xl shadow-primary/25 text-base"
            >
              Start Free — No Credit Card Needed
            </Button>
          </Link>
        </FadeIn>
      </section>
    </div>
  );
}
