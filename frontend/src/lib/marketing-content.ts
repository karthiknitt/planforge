/**
 * Single source of truth for marketing-site content shared across the landing
 * page (`app/(marketing)/page.tsx`), the pricing page
 * (`app/(marketing)/pricing/page.tsx`), and the how-it-works page
 * (`app/(marketing)/how-it-works/page.tsx`) — including the JSON-LD blocks
 * each of those pages embeds.
 *
 * Plain hardcoded English strings — the marketing routes are not wired into
 * the app's i18n system (`messages/{en,hi,ta}.json`), so this module
 * intentionally does not route through `next-intl`.
 */
import type { LucideIcon } from "lucide-react";
import { Download, Eye, Settings2, Zap } from "lucide-react";
import { TIER_ORDER } from "@/lib/plan";

/* ──────────────────────────────────────────────────────────────
   Archetype count — the one fact both pricing tiers and the
   how-it-works steps embed. Confirmed 5 (Layout A–E: front, centre,
   rear, corner, open-plan) against how-it-works' detailed per-layout
   breakdown; landing's "3" was stale.
────────────────────────────────────────────────────────────── */
export const ARCHETYPE_COUNT = 5;
export const ARCHETYPE_NAMES = [
  "Front staircase",
  "Centre staircase",
  "Rear staircase",
  "Corner entry",
  "Open-plan kitchen/dining",
] as const;

/* ──────────────────────────────────────────────────────────────
   Pricing tiers
────────────────────────────────────────────────────────────── */
export type PricingTierId = (typeof TIER_ORDER)[number];
export type CheckoutPlan = Exclude<PricingTierId, "free">;

export interface PricingTier {
  id: PricingTierId;
  name: string;
  price: string;
  period: string;
  tagline: string;
  highlight: boolean;
  cta: string;
  /** Which plan id the checkout button should post — null for the free tier (no checkout). */
  checkoutPlan: CheckoutPlan | null;
  /** Short bullet list for compact cards (landing's pricing preview section). */
  perks: string[];
  /** Full feature-comparison list with included/excluded flags (dedicated pricing page). */
  features: Array<{ text: string; included: boolean }>;
}

export const pricingTiers: PricingTier[] = [
  {
    id: "free",
    name: "Free",
    price: "₹0",
    period: "/month",
    tagline: "Try it out, no commitment.",
    highlight: false,
    cta: "Get Started Free",
    checkoutPlan: null,
    perks: ["3 projects", `All ${ARCHETYPE_COUNT} layout archetypes`, "PDF export"],
    features: [
      { text: "3 saved projects", included: true },
      { text: `All ${ARCHETYPE_COUNT} layout archetypes`, included: true },
      { text: "NBC 2016 compliance checks", included: true },
      { text: "PDF export (1:100 scale)", included: true },
      { text: "DXF export for AutoCAD", included: false },
      { text: "BOQ Excel export", included: false },
      { text: "Priority support", included: false },
    ],
  },
  {
    id: "basic",
    name: "Basic",
    price: "₹499",
    period: "/month",
    tagline: "For active builders and designers.",
    highlight: true,
    cta: "Subscribe — ₹499/mo",
    checkoutPlan: "basic",
    perks: ["Unlimited projects", "PDF + DXF export", "NBC compliance checks"],
    features: [
      { text: "Unlimited saved projects", included: true },
      { text: `All ${ARCHETYPE_COUNT} layout archetypes`, included: true },
      { text: "NBC 2016 compliance checks", included: true },
      { text: "PDF export (1:100 scale)", included: true },
      { text: "DXF export for AutoCAD", included: true },
      { text: "BOQ Excel export", included: false },
      { text: "Priority support", included: false },
    ],
  },
  {
    id: "pro",
    name: "Pro",
    price: "₹999",
    period: "/month",
    tagline: "For professionals delivering to clients.",
    highlight: false,
    cta: "Subscribe — ₹999/mo",
    checkoutPlan: "pro",
    perks: ["Everything in Basic", "BOQ Excel export", "Priority support"],
    features: [
      { text: "Unlimited saved projects", included: true },
      { text: `All ${ARCHETYPE_COUNT} layout archetypes`, included: true },
      { text: "NBC 2016 compliance checks", included: true },
      { text: "PDF export (1:100 scale)", included: true },
      { text: "DXF export for AutoCAD", included: true },
      { text: "BOQ Excel export", included: true },
      { text: "Priority support", included: true },
      { text: "Team / multi-seat access", included: false },
    ],
  },
  {
    id: "firm",
    name: "Firm",
    price: "₹2,999",
    period: "/month",
    tagline: "For civil engineering firms with multiple engineers.",
    highlight: false,
    cta: "Subscribe — ₹2,999/mo",
    checkoutPlan: "firm",
    perks: ["Everything in Pro", "Up to 5 engineers", "Team admin dashboard"],
    features: [
      { text: "Everything in Pro", included: true },
      { text: "Up to 5 engineers", included: true },
      { text: "Shared project pool", included: true },
      { text: "Team admin dashboard", included: true },
      { text: "DXF export for AutoCAD", included: true },
      { text: "BOQ Excel export", included: true },
      { text: "Priority support", included: true },
      { text: "Team / multi-seat access", included: true },
    ],
  },
];

/* ──────────────────────────────────────────────────────────────
   How-it-works steps
   4 steps total (verified against how-it-works' detailed per-step
   breakdown, including the named A–E archetype list on step 2 —
   landing's "three steps" heading and 3-step array were stale).
   `text` is the concise one-liner reused verbatim as both the
   landing teaser card description and the HowTo JSON-LD step text —
   landing shows all 4 steps rather than an invented shorter subset.
────────────────────────────────────────────────────────────── */
export interface HowItWorksStep {
  num: string;
  icon: LucideIcon;
  title: string;
  subtitle: string;
  text: string;
  points: string[];
}

export const howItWorksSteps: HowItWorksStep[] = [
  {
    num: "01",
    icon: Settings2,
    title: "Enter Your Plot",
    subtitle: "All the details that drive the layout engine",
    text: "Input plot dimensions, city, setbacks on all 4 sides, road-facing direction, BHK count (1–4), and optional rooms.",
    points: [
      "Plot length × width in metres",
      "Setbacks on all 4 sides (N/S/E/W)",
      "Road-facing direction and north orientation",
      "City (Bangalore, Chennai, Delhi, Hyderabad, Pune, or Other)",
      "Road width for FAR calculation",
      "BHK count (1, 2, 3, or 4)",
      "Optional rooms: pooja room, study, balcony",
    ],
  },
  {
    num: "02",
    icon: Zap,
    title: "Instant Layout Generation",
    subtitle: `${ARCHETYPE_COUNT} archetypes, each NBC-checked in under a second`,
    text: `PlanForge generates all ${ARCHETYPE_COUNT} archetypes simultaneously and checks each against NBC 2016 and city-specific rules.`,
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
  },
  {
    num: "03",
    icon: Eye,
    title: "Review in Browser",
    subtitle: "Interactive CAD-grade SVG preview",
    text: "Inspect colour-coded rooms, double-line walls, door arcs, dimension lines, and north arrow in the interactive SVG preview.",
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
  },
  {
    num: "04",
    icon: Download,
    title: "Export & Build",
    subtitle: "Everything you need to move from screen to site",
    text: "Download a 1:100 scale PDF, AutoCAD DXF with 9 named layers, or BOQ Excel with 11 quantity line items.",
    points: [
      "PDF — 1:100 scale, A3 or A4, with title block and dimensions",
      "DXF — AutoCAD-ready with 9 named layers (A-WALL-BRICK, A-DOOR, S-COLUMN, DIM-LINE, …)",
      "BOQ Excel — 11 quantity line items: masonry, concrete, steel, plaster, flooring, excavation",
      "Download all from the project view — no extra steps",
      "Works on Free plan (PDF only) — DXF and BOQ with Basic/Pro",
    ],
  },
];

/* ──────────────────────────────────────────────────────────────
   FAQ
   Design: one master list, each entry tagged with which page(s) it
   appears on. The 3 questions that used to have diverged answers on
   landing vs pricing (AutoCAD/software, cities supported, compliance
   standard) now have a single canonical answer consumed identically
   by both pages. Page-specific questions (landing: free-plan,
   irregular plots, export formats; pricing: cancel-anytime, BOQ
   explainer) are preserved as-is, tagged to their one page.
────────────────────────────────────────────────────────────── */
export interface FaqEntry {
  q: string;
  a: string;
  pages: Array<"landing" | "pricing">;
}

export const faqEntries: FaqEntry[] = [
  // ── Shared/core — canonical answers, appear on both pages ──
  {
    q: "Do I need AutoCAD or any software to use PlanForge?",
    a: "No. PlanForge runs entirely in your browser — nothing to install. You can view, edit, and export floor plans from any laptop or phone on the construction site. DXF export is available for Basic and Pro subscribers who want to open plans in AutoCAD, BricsCAD, or any other CAD tool.",
    pages: ["landing", "pricing"],
  },
  {
    q: "Which Indian cities are supported?",
    a: "Bangalore, Chennai, Delhi, Hyderabad, Pune, and a generic Indian standard option that applies NBC 2016 defaults. City-specific setbacks and FAR tables are baked in for each supported city.",
    pages: ["landing", "pricing"],
  },
  {
    q: "What compliance standard does PlanForge use?",
    a: "PlanForge enforces NBC 2016 (National Building Code) for room areas, minimum widths, stair tread/riser dimensions, and ventilation ratios. City-specific setbacks and floor area ratios (FAR) are applied on top of the national baseline.",
    pages: ["landing", "pricing"],
  },
  // ── Landing-only ──
  {
    q: "Is the free plan really free?",
    a: `Yes — no credit card required. The free plan lets you create up to 3 projects with all ${ARCHETYPE_COUNT} layout archetypes and PDF export. Upgrade to Basic (₹499/mo) for DXF export or Pro (₹999/mo) for BOQ Excel.`,
    pages: ["landing"],
  },
  {
    q: "Can I use PlanForge for L-shaped or irregular plots?",
    a: "Currently PlanForge supports rectangular and L-shaped plots. Quadrilateral and fully irregular plot support is on the roadmap.",
    pages: ["landing"],
  },
  {
    q: "What file formats can I export?",
    a: "PDF (1:100 scale, A3/A4 with title block) on all plans. DXF for AutoCAD with 9 named layers on Basic+. BOQ Excel with 11 quantity line items on Pro.",
    pages: ["landing"],
  },
  // ── Pricing-only ──
  {
    q: "Can I cancel anytime?",
    a: "Yes. You can cancel your subscription at any time from your account settings. Your access continues until the end of the current billing period, and you won't be charged again.",
    pages: ["pricing"],
  },
  {
    q: "What is a BOQ?",
    a: "A Bill of Quantities (BOQ) is a breakdown of construction materials with estimated quantities — masonry, concrete, structural steel, plaster, flooring, and more. PlanForge auto-calculates 11 quantity line items and lets you export them to Excel for cost estimation.",
    pages: ["pricing"],
  },
];

export function getFaqsForPage(page: "landing" | "pricing"): FaqEntry[] {
  return faqEntries.filter((entry) => entry.pages.includes(page));
}
