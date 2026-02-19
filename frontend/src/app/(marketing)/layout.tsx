import { Building2 } from "lucide-react";
import Link from "next/link";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { MobileNav } from "./mobile-nav";

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* Sticky Nav */}
      <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur-sm">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 items-center justify-between">
            {/* Logo */}
            <Link href="/" className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-md bg-[#1e3a5f]">
                <Building2 className="h-5 w-5 text-white" />
              </div>
              <span className="text-xl font-bold tracking-tight text-[#1e3a5f]">PlanForge</span>
            </Link>

            {/* Center nav links */}
            <nav className="hidden md:flex items-center gap-8">
              <Link
                href="/how-it-works"
                className="text-sm font-medium text-slate-600 hover:text-[#1e3a5f] transition-colors"
              >
                How It Works
              </Link>
              <Link
                href="/pricing"
                className="text-sm font-medium text-slate-600 hover:text-[#1e3a5f] transition-colors"
              >
                Pricing
              </Link>
            </nav>

            {/* Right actions */}
            <div className="hidden md:flex items-center gap-3">
              <ThemeToggle />
              <Link href="/sign-in">
                <Button variant="ghost" size="sm" className="text-slate-600 hover:text-[#1e3a5f]">
                  Sign In
                </Button>
              </Link>
              <Link href="/sign-up">
                <Button
                  size="sm"
                  className="bg-[#f97316] hover:bg-[#ea6c0a] text-white font-semibold"
                >
                  Get Started Free
                </Button>
              </Link>
            </div>
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
      <footer className="border-t border-slate-100 bg-slate-50">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-10">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <div className="flex h-6 w-6 items-center justify-center rounded bg-[#1e3a5f]">
                <Building2 className="h-4 w-4 text-white" />
              </div>
              <span className="font-bold text-[#1e3a5f]">PlanForge</span>
            </div>
            <nav className="flex items-center gap-6 text-sm text-slate-500">
              <Link href="/how-it-works" className="hover:text-[#1e3a5f] transition-colors">
                How It Works
              </Link>
              <Link href="/pricing" className="hover:text-[#1e3a5f] transition-colors">
                Pricing
              </Link>
              <Link href="/sign-in" className="hover:text-[#1e3a5f] transition-colors">
                Sign In
              </Link>
            </nav>
            <p className="text-sm text-slate-400">
              © {new Date().getFullYear()} PlanForge. All rights reserved.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
