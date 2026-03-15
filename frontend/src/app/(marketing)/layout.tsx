import Link from "next/link";
import { PlanForgeIcon } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { MobileNav } from "./mobile-nav";

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* ── Sticky Nav ── */}
      <header className="sticky top-0 z-50 border-b border-border/60 bg-background/85 backdrop-blur-xl">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 items-center justify-between gap-4">
            {/* Logo */}
            <Link href="/" className="flex items-center gap-3 group flex-shrink-0">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-orange-500 to-amber-600 shadow-lg shadow-orange-500/25 transition-all group-hover:shadow-orange-500/50 group-hover:scale-105">
                <PlanForgeIcon className="h-5 w-5 text-white" />
              </div>
              <span
                className="text-2xl font-black tracking-tight"
                style={{ fontFamily: "var(--font-display)" }}
              >
                Plan<span className="text-primary">Forge</span>
              </span>
            </Link>

            {/* Center nav links — visible from md+ (768px) — proper laptop breakpoint */}
            <nav className="hidden md:flex items-center gap-1 flex-1 justify-center">
              <Link
                href="/how-it-works"
                className="px-4 py-2 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-all"
              >
                How It Works
              </Link>
              <Link
                href="/gallery"
                className="px-4 py-2 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-all"
              >
                Gallery
              </Link>
              <Link
                href="/pricing"
                className="px-4 py-2 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-all"
              >
                Pricing
              </Link>
            </nav>

            {/* Right actions — visible from md+ */}
            <div className="hidden md:flex items-center gap-2 flex-shrink-0">
              <ThemeToggle />
              <Link href="/sign-in">
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-muted-foreground hover:text-foreground font-medium"
                >
                  Sign In
                </Button>
              </Link>
              <Link href="/sign-up">
                <Button
                  size="sm"
                  className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold btn-shine shadow-md shadow-primary/25 px-5"
                >
                  Get Started Free
                </Button>
              </Link>
            </div>

            {/* Mobile — only on < md */}
            <div className="flex md:hidden items-center gap-2">
              <ThemeToggle />
              <MobileNav />
            </div>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1">{children}</main>

      {/* Footer */}
      <footer className="border-t border-border bg-card/30">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-12 lg:py-16">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 lg:gap-12 mb-10">
            {/* Brand column */}
            <div className="space-y-3">
              <Link href="/" className="flex items-center gap-2.5 w-fit group">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-orange-500 to-amber-600 shadow-md shadow-orange-500/20 transition-all group-hover:scale-105">
                  <PlanForgeIcon className="h-4 w-4 text-white" />
                </div>
                <span className="text-xl font-black" style={{ fontFamily: "var(--font-display)" }}>
                  Plan<span className="text-primary">Forge</span>
                </span>
              </Link>
              <p className="text-sm text-muted-foreground leading-relaxed max-w-xs">
                G+1 floor plan generator for Indian builders. NBC 2016 compliant. 5 layouts, PDF &
                DXF export.
              </p>
            </div>

            {/* Product links */}
            <div className="space-y-3">
              <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">
                Product
              </p>
              <nav className="flex flex-col gap-2">
                <Link
                  href="/how-it-works"
                  className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                >
                  How It Works
                </Link>
                <Link
                  href="/gallery"
                  className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                >
                  Floor Plan Gallery
                </Link>
                <Link
                  href="/pricing"
                  className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                >
                  Pricing
                </Link>
              </nav>
            </div>

            {/* Account links */}
            <div className="space-y-3">
              <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">
                Account
              </p>
              <nav className="flex flex-col gap-2">
                <Link
                  href="/sign-in"
                  className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                >
                  Sign In
                </Link>
                <Link
                  href="/sign-up"
                  className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                >
                  Sign Up Free
                </Link>
              </nav>
            </div>
          </div>

          {/* Bottom bar */}
          <div className="pt-8 border-t border-border/50 flex flex-col sm:flex-row items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground/60">
              &copy; {new Date().getFullYear()} PlanForge. All rights reserved.
            </p>
            <p className="text-xs text-muted-foreground/40">
              Built for Indian civil engineers & builders
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
