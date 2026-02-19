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
      <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur-sm">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <Link href="/dashboard" className="flex items-center gap-2">
            <Building2 className="h-5 w-5 text-[#1e3a5f]" />
            <span className="font-bold text-[#1e3a5f]">PlanForge</span>
          </Link>
          <div className="flex items-center gap-3">
            {session && (
              <>
                <Link
                  href="/account"
                  className="hidden sm:block text-sm text-muted-foreground hover:text-foreground transition-colors"
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
