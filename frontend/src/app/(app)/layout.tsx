import { Building2 } from "lucide-react";
import { headers } from "next/headers";
import Link from "next/link";
import { ThemeToggle } from "@/components/theme-toggle";
import { auth } from "@/lib/auth";
import { SignOutButton } from "./dashboard/sign-out-button";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await auth.api.getSession({ headers: await headers() });

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="sticky top-0 z-40 border-b border-border/50 bg-background/85 backdrop-blur-xl">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <Link href="/dashboard" className="flex items-center gap-2.5 group">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-orange-500 to-amber-600 shadow-lg shadow-orange-500/20 transition-all group-hover:shadow-orange-500/40 group-hover:scale-105">
              <Building2 className="h-3.5 w-3.5 text-white" />
            </div>
            <span
              className="font-bold tracking-tight"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Plan<span className="text-[#f97316]">Forge</span>
            </span>
          </Link>
          <div className="flex items-center gap-3">
            {session && (
              <>
                <Link
                  href="/account"
                  className="hidden sm:block text-sm text-muted-foreground hover:text-foreground transition-colors font-medium"
                >
                  {session.user.email}
                </Link>
                <SignOutButton />
              </>
            )}
            <ThemeToggle />
          </div>
        </div>
      </header>
      <div className="flex-1">{children}</div>
    </div>
  );
}
