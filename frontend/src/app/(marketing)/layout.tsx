import Link from "next/link";
import { PlanForgeIcon } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { MobileNav } from "./mobile-nav";

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* ── Sticky Nav ── */}
      <header className="sticky top-0 z-50 border-b border-border/30 bg-background/70 backdrop-blur-xl">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 items-center justify-between gap-4">
            {/* Logo */}
            <Link href="/" className="flex items-center gap-2.5 group flex-shrink-0">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-orange-500 to-amber-600 shadow-lg shadow-orange-500/15 transition-all group-hover:shadow-orange-500/30 group-hover:scale-105">
                <PlanForgeIcon className="h-4 w-4 text-white" />
              </div>
              <span
                className="text-xl font-black tracking-tight"
                style={{ fontFamily: "var(--font-display)" }}
              >
                Plan<span className="text-primary">Forge</span>
              </span>
            </Link>

            {/* Center nav links */}
            <nav className="hidden sm:flex items-center gap-1 flex-1 justify-center">
              <Link
                href="/how-it-works"
                className="px-4 py-2 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-all"
              >
                How It Works
              </Link>
              <Link
                href="/pricing"
                className="px-4 py-2 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-all"
              >
                Pricing
              </Link>
            </nav>

            {/* Right actions */}
            <div className="hidden sm:flex items-center gap-3 flex-shrink-0">
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
                  className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold btn-shine shadow-sm shadow-primary/15 px-5"
                >
                  Get Started Free
                </Button>
              </Link>
            </div>

            {/* Mobile */}
            <div className="flex sm:hidden items-center gap-2">
              <ThemeToggle />
              <MobileNav />
            </div>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1">{children}</main>

      {/* Footer */}
      <footer className="border-t border-border/30 bg-card/20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-12">
          <div className="flex flex-col md:flex-row items-center justify-between gap-6">
            <div className="flex items-center gap-2.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-orange-500 to-amber-600">
                <PlanForgeIcon className="h-3.5 w-3.5 text-white" />
              </div>
              <span className="text-lg font-black" style={{ fontFamily: "var(--font-display)" }}>
                Plan<span className="text-primary">Forge</span>
              </span>
            </div>
            <nav className="flex items-center gap-8 text-sm text-muted-foreground/60">
              <Link href="/how-it-works" className="hover:text-foreground transition-colors">
                How It Works
              </Link>
              <Link href="/pricing" className="hover:text-foreground transition-colors">
                Pricing
              </Link>
              <Link href="/sign-in" className="hover:text-foreground transition-colors">
                Sign In
              </Link>
            </nav>
            <p className="text-xs text-muted-foreground/60">
              &copy; {new Date().getFullYear()} PlanForge
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
