"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/lib/auth-client";
import { navSessionState } from "@/lib/nav-session-state";
import { UserMenu } from "../(app)/user-menu";

export function NavSessionActions() {
  const session = useSession();
  const state = navSessionState(session);

  if (state === "pending") {
    return (
      <div className="flex items-center gap-2" aria-hidden="true">
        <Skeleton className="h-9 w-20 rounded-md" />
        <Skeleton className="h-9 w-32 rounded-md" />
      </div>
    );
  }

  if (state === "authenticated" && session.data) {
    return (
      <>
        <Link href="/dashboard">
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground hover:text-foreground font-medium"
          >
            Dashboard
          </Button>
        </Link>
        <UserMenu name={session.data.user.name} email={session.data.user.email} />
      </>
    );
  }

  return (
    <>
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
    </>
  );
}

export function FooterSessionLinks() {
  const state = navSessionState(useSession());

  if (state === "pending") {
    return (
      <div className="flex flex-col gap-2" aria-hidden="true">
        <Skeleton className="h-5 w-20" />
        <Skeleton className="h-5 w-24" />
      </div>
    );
  }

  if (state === "authenticated") {
    return (
      <Link
        href="/dashboard"
        className="text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        Dashboard
      </Link>
    );
  }

  return (
    <>
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
    </>
  );
}
