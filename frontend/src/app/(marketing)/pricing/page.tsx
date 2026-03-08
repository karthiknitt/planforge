import { CheckCircle, X } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { PricingCheckoutButton } from "@/components/pricing-checkout-button";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "Pricing \u2014 PlanForge",
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
    price: "\u20B90",
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
    price: "\u20B9499",
    period: "/month",
    tagline: "For active builders and designers.",
    highlight: true,
    cta: "Subscribe \u20B9499/mo",
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
    price: "\u20B9999",
    period: "/month",
    tagline: "For professionals delivering to clients.",
    highlight: false,
    cta: "Subscribe \u20B9999/mo",
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
    a: "No. PlanForge runs entirely in your browser \u2014 no software to install. DXF export is available for Basic and Pro subscribers who want to open plans in AutoCAD, BricsCAD, or any other CAD tool.",
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
    a: "Yes. You can cancel your subscription at any time from your account settings. Your access continues until the end of the current billing period, and you won\u2019t be charged again.",
  },
  {
    q: "What is a BOQ?",
    a: "A Bill of Quantities (BOQ) is a breakdown of construction materials with estimated quantities \u2014 masonry, concrete, structural steel, plaster, flooring, and more. PlanForge auto-calculates 11 quantity line items and lets you export them to Excel for cost estimation.",
  },
];

export default function PricingPage() {
  return (
    <div className="bg-background">
      {/* Header */}
      <section className="py-20 lg:py-24 bg-gradient-to-b from-card/30 to-background border-b border-border/30">
        <div className="animate-fade-up mx-auto max-w-4xl px-4 text-center">
          <p className="text-xs font-bold text-primary uppercase tracking-[0.2em] mb-4">Pricing</p>
          <h1
            className="text-4xl lg:text-5xl font-black text-foreground mb-4"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Simple, Transparent Pricing
          </h1>
          <p className="text-lg text-muted-foreground max-w-lg mx-auto">
            Start free. Upgrade when you need more power.
          </p>
        </div>
      </section>

      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Pricing cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 lg:gap-6 max-w-5xl mx-auto py-16 lg:py-20">
          {plans.map((plan, i) => (
            <Card
              key={plan.name}
              className={`animate-fade-up relative flex flex-col transition-all h-full rounded-2xl backdrop-blur-sm ${
                plan.highlight
                  ? "border-primary/40 shadow-2xl shadow-primary/10 bg-card glow-card"
                  : "border-border/40 shadow-sm bg-card/50 hover:border-border/60"
              }`}
              style={{ animationDelay: `${100 + i * 100}ms` }}
            >
              {plan.highlight && (
                <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 bg-primary text-primary-foreground text-[10px] font-bold px-5 py-1.5 rounded-full shadow-lg shadow-primary/25 uppercase tracking-wider">
                  Most Popular
                </div>
              )}

              <CardHeader className="pt-8 pb-4">
                <p className="text-[10px] font-bold text-muted-foreground/70 uppercase tracking-[0.2em] mb-1">
                  {plan.name}
                </p>
                <div className="flex items-baseline gap-1 mb-2">
                  <span
                    className="text-5xl font-black text-foreground"
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    {plan.price}
                  </span>
                  <span className="text-muted-foreground/60 text-sm">{plan.period}</span>
                </div>
                <p className="text-sm text-muted-foreground">{plan.tagline}</p>
              </CardHeader>

              <CardContent className="flex-1 flex flex-col gap-6">
                <ul className="space-y-3">
                  {plan.features.map((f) => (
                    <li key={f.text} className="flex items-start gap-3">
                      {f.included ? (
                        <CheckCircle className="h-4 w-4 text-primary flex-shrink-0 mt-0.5" />
                      ) : (
                        <X className="h-4 w-4 text-muted-foreground/50 flex-shrink-0 mt-0.5" />
                      )}
                      <span
                        className={`text-sm ${f.included ? "text-foreground/80" : "text-muted-foreground/60"}`}
                      >
                        {f.text}
                      </span>
                    </li>
                  ))}
                </ul>

                <div className="mt-auto pt-2">
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
                        className="w-full font-bold border-border/50 text-foreground hover:bg-muted"
                      >
                        {plan.cta}
                      </Button>
                    </Link>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* FAQ */}
        <div className="max-w-3xl mx-auto pb-20">
          <h2
            className="animate-fade-up text-2xl font-black text-foreground mb-10 text-center"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Frequently Asked Questions
          </h2>
          <Accordion type="single" collapsible className="space-y-3">
            {faqs.map((faq) => (
              <AccordionItem
                key={faq.q}
                value={faq.q}
                className="border border-border/40 bg-card/30 rounded-xl px-6 shadow-sm"
              >
                <AccordionTrigger className="text-left text-sm font-semibold text-foreground hover:no-underline py-5">
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
      <section className="py-20 relative overflow-hidden bg-gradient-to-br from-primary/[0.06] via-card/20 to-background border-t border-border/30">
        <div className="absolute inset-0 bg-blueprint-grid opacity-25" />
        <div className="animate-fade-up relative text-center px-4">
          <p className="text-muted-foreground mb-6 text-lg">
            Still have questions? Start for free &mdash; no credit card required.
          </p>
          <Link href="/sign-up">
            <Button
              size="lg"
              className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-10 h-12 btn-shine shadow-lg shadow-primary/15"
            >
              Start Free
            </Button>
          </Link>
        </div>
      </section>
    </div>
  );
}
