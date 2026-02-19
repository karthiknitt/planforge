"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";

export function MobileNav() {
  const [open, setOpen] = useState(false);

  return (
    <div className="md:hidden">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() => setOpen((v) => !v)}
        aria-label="Toggle menu"
      >
        {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
      </Button>

      {open && (
        <div className="absolute left-0 right-0 top-16 z-50 border-b bg-white shadow-md">
          <nav className="flex flex-col px-4 py-4 gap-1">
            <Link
              href="/how-it-works"
              onClick={() => setOpen(false)}
              className="rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:text-[#1e3a5f]"
            >
              How It Works
            </Link>
            <Link
              href="/pricing"
              onClick={() => setOpen(false)}
              className="rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:text-[#1e3a5f]"
            >
              Pricing
            </Link>
            <Link
              href="/sign-in"
              onClick={() => setOpen(false)}
              className="rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:text-[#1e3a5f]"
            >
              Sign In
            </Link>
            <Link href="/sign-up" onClick={() => setOpen(false)}>
              <Button
                size="sm"
                className="w-full mt-1 bg-[#f97316] hover:bg-[#ea6c0a] text-white font-semibold"
              >
                Get Started Free
              </Button>
            </Link>
          </nav>
        </div>
      )}
    </div>
  );
}
