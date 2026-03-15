import type { Metadata } from "next";
import Link from "next/link";
import { FadeIn } from "@/components/motion/fade-in";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { GalleryClient, type GalleryPlan } from "./gallery-client";

// ── Metadata ──────────────────────────────────────────────────────────────────

export const metadata: Metadata = {
  title: "Floor Plan Templates for Indian Homes | PlanForge",
  description:
    "Browse 2BHK, 3BHK and 4BHK floor plan templates for 20×30, 30×40 and 40×60 ft plots. NBC-compliant layouts for Chennai, Bangalore and other Indian cities. Customize and export instantly.",
  openGraph: {
    title: "Floor Plan Templates — 2BHK, 3BHK, 4BHK | PlanForge",
    description:
      "Browse NBC-compliant floor plan templates for Indian residential plots. Customize any template with your dimensions and get PDF + DXF exports.",
    type: "website",
  },
  keywords: [
    "20x30 floor plan",
    "30x40 house design",
    "2BHK floor plan India",
    "3BHK house plan 30x40",
    "Indian house floor plan",
    "NBC compliant floor plan",
    "Chennai house plan",
    "Bangalore house plan",
    "floor plan generator India",
  ],
};

// ── Data fetching ─────────────────────────────────────────────────────────────

async function fetchGalleryPlans(): Promise<GalleryPlan[]> {
  const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";
  try {
    const res = await fetch(`${backendUrl}/api/gallery/plans`, {
      // Revalidate every 24 h — plans are stable but we want fresh data after deploys
      next: { revalidate: 86400 },
    });
    if (!res.ok) return [];
    return (await res.json()) as GalleryPlan[];
  } catch {
    return [];
  }
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function GalleryPage() {
  const plans = await fetchGalleryPlans();

  return (
    <>
      {/* ── HERO ── */}
      <section className="relative overflow-hidden bg-background border-b border-border/50 py-16 lg:py-20">
        <div className="absolute inset-0 bg-blueprint-grid opacity-60" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_0%,rgba(249,115,22,0.08)_0%,transparent_60%)]" />

        <FadeIn className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 text-center">
          <Badge className="mb-5 bg-primary/10 text-primary border-primary/30 hover:bg-primary/15 px-4 py-1.5">
            Template Gallery
          </Badge>
          <h1
            className="text-4xl sm:text-5xl lg:text-6xl font-black tracking-tight text-foreground leading-tight mb-5"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Browse Floor Plans
          </h1>
          <p className="text-lg md:text-xl text-muted-foreground mb-8 max-w-2xl mx-auto leading-relaxed">
            3,000+ Indian builders use PlanForge. Start with a template — pick any layout, customize
            your dimensions, and get NBC-compliant PDF + DXF exports instantly.
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <Link href="/sign-up">
              <Button
                size="lg"
                className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-8 h-11 btn-shine shadow-lg shadow-primary/25"
              >
                Start for Free
              </Button>
            </Link>
            <Link href="/how-it-works">
              <Button
                size="lg"
                variant="outline"
                className="border-border/80 text-foreground hover:bg-muted font-semibold px-8 h-11"
              >
                How It Works
              </Button>
            </Link>
          </div>
        </FadeIn>
      </section>

      {/* ── GALLERY ── */}
      <section className="py-12 lg:py-16 bg-background">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          {plans.length === 0 ? (
            <div className="text-center py-20">
              <p className="text-muted-foreground mb-4">
                Gallery is loading. Please start the backend server.
              </p>
              <Link href="/sign-up">
                <Button className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold">
                  Sign up to generate your own plan
                </Button>
              </Link>
            </div>
          ) : (
            <GalleryClient plans={plans} />
          )}
        </div>
      </section>

      {/* ── BOTTOM CTA ── */}
      <section className="py-16 lg:py-20 bg-muted/20 border-t border-border/50">
        <FadeIn className="mx-auto max-w-3xl px-4 text-center">
          <h2
            className="text-2xl md:text-3xl font-black text-foreground mb-3"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Don&apos;t see your plot size?
          </h2>
          <p className="text-muted-foreground text-base mb-7">
            Enter any dimensions and get custom layouts generated in under a second.
          </p>
          <Link href="/sign-up">
            <Button
              size="lg"
              className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-10 h-11 btn-shine shadow-lg shadow-primary/25"
            >
              Generate a Custom Plan
            </Button>
          </Link>
          <p className="mt-4 text-xs text-muted-foreground/60">
            Powered by{" "}
            <Link href="/" className="text-primary hover:underline underline-offset-4">
              PlanForge
            </Link>
          </p>
        </FadeIn>
      </section>
    </>
  );
}
