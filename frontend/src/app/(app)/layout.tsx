import { PlanForgeIcon } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { auth } from "@/lib/auth";
import { headers } from "next/headers";
import Link from "next/link";
import { UserMenu } from "./user-menu";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await auth.api.getSession({ headers: await headers() });

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="sticky top-0 z-40 border-b border-border/60 bg-background/90 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8 h-16">
          {/* Logo */}
          <Link href="/dashboard" className="flex items-center gap-2.5 group flex-shrink-0">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-orange-500 to-amber-600 shadow-lg shadow-orange-500/20 transition-all group-hover:shadow-orange-500/40 group-hover:scale-105">
              <PlanForgeIcon className="h-4 w-4 text-white" />
            </div>
            <span
              className="text-lg font-black tracking-tight"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Plan<span className="text-primary">Forge</span>
            </span>
          </Link>

          {/* Center nav */}
          <nav className="hidden md:flex items-center gap-1">
            <Link
              href="/dashboard"
              className="px-4 py-2 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-all"
            >
              Dashboard
            </Link>
            <Link
              href="/projects/new"
              className="px-4 py-2 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-all"
            >
              New Project
            </Link>
            <Link
              href="/pricing"
              className="px-4 py-2 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-all"
            >
              Upgrade
            </Link>
          </nav>

          {/* Right */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <ThemeToggle />
            {session && (
              <UserMenu name={session.user.name} email={session.user.email} />
            )}
          </div>
        </div>
      </header>
      <div className="flex-1">{children}</div>
    </div>
  );
}
