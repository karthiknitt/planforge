import { CheckCircle, X } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "Pricing — PlanForge",
  description: "Simple, transparent pricing for PlanForge floor plan generator.",
};

const plans = [
  {
    name: "Free",
    price: "₹0",
    period: "/month",
    tagline: "Try it out, no commitment.",
    highlight: false,
    cta: "Get Started Free",
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
    cta: "Subscribe",
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
    cta: "Subscribe",
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
    <div className="py-20 bg-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center mb-16">
          <h1 className="text-4xl font-extrabold text-[#1e3a5f] mb-3">
            Simple, Transparent Pricing
          </h1>
          <p className="text-xl text-slate-500">Start free. Upgrade when you need more.</p>
        </div>

        {/* Pricing cards */}
        <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto mb-20">
          {plans.map((plan) => (
            <Card
              key={plan.name}
              className={`relative flex flex-col ${
                plan.highlight
                  ? "border-[#f97316] shadow-2xl shadow-[#f97316]/10 scale-[1.03]"
                  : "border-slate-200 shadow-sm"
              }`}
            >
              {plan.highlight && (
                <div className="absolute -top-4 left-1/2 -translate-x-1/2 bg-[#f97316] text-white text-xs font-bold px-5 py-1.5 rounded-full shadow">
                  Most Popular
                </div>
              )}

              <CardHeader className="pt-8 pb-4">
                <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">
                  {plan.name}
                </p>
                <div className="flex items-baseline gap-1 mb-1">
                  <span className="text-5xl font-extrabold text-[#1e3a5f]">{plan.price}</span>
                  <span className="text-slate-400 text-sm">{plan.period}</span>
                </div>
                <p className="text-sm text-slate-500">{plan.tagline}</p>
              </CardHeader>

              <CardContent className="flex-1 flex flex-col gap-6">
                {/* Feature list */}
                <ul className="space-y-3">
                  {plan.features.map((f) => (
                    <li key={f.text} className="flex items-start gap-3">
                      {f.included ? (
                        <CheckCircle className="h-4 w-4 text-[#f97316] flex-shrink-0 mt-0.5" />
                      ) : (
                        <X className="h-4 w-4 text-slate-300 flex-shrink-0 mt-0.5" />
                      )}
                      <span
                        className={`text-sm ${f.included ? "text-slate-700" : "text-slate-400"}`}
                      >
                        {f.text}
                      </span>
                    </li>
                  ))}
                </ul>

                {/* CTA */}
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

        {/* FAQ */}
        <div className="max-w-3xl mx-auto">
          <h2 className="text-2xl font-extrabold text-[#1e3a5f] mb-8 text-center">
            Frequently Asked Questions
          </h2>
          <Accordion type="single" collapsible className="space-y-2">
            {faqs.map((faq) => (
              <AccordionItem
                key={faq.q}
                value={faq.q}
                className="border border-slate-100 rounded-lg px-5 shadow-sm"
              >
                <AccordionTrigger className="text-left text-sm font-semibold text-[#1e3a5f] hover:no-underline py-4">
                  {faq.q}
                </AccordionTrigger>
                <AccordionContent className="text-sm text-slate-600 leading-relaxed pb-4">
                  {faq.a}
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </div>

        {/* Bottom CTA */}
        <div className="mt-16 text-center">
          <p className="text-slate-500 mb-4">Still have questions?</p>
          <Link href="/sign-up">
            <Button className="bg-[#f97316] hover:bg-[#ea6c0a] text-white font-bold px-8">
              Start Free — No Credit Card Needed
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
