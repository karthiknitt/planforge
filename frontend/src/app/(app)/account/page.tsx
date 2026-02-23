import { eq } from "drizzle-orm";
import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";
import { FadeIn } from "@/components/motion/fade-in";
import { Button } from "@/components/ui/button";
import { db } from "@/db";
import { user as userTable } from "@/db/schema";
import { auth } from "@/lib/auth";

export const metadata: Metadata = { title: "Account — PlanForge" };

const TIER_BADGE = {
  free: {
    label: "Free",
    className: "bg-muted text-muted-foreground border border-border",
  },
  basic: {
    label: "Basic",
    className: "bg-primary/10 text-primary/70 border border-primary/20",
  },
  pro: {
    label: "Pro",
    className: "bg-primary/15 text-primary border border-primary/25",
  },
};

export default async function AccountPage() {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/sign-in");

  const userRows = await db
    .select({ planTier: userTable.planTier, planExpiresAt: userTable.planExpiresAt })
    .from(userTable)
    .where(eq(userTable.id, session.user.id))
    .limit(1);

  const planTier = userRows[0]?.planTier ?? "free";
  const planExpiresAt = userRows[0]?.planExpiresAt ?? null;
  const badge = TIER_BADGE[planTier as keyof typeof TIER_BADGE] ?? TIER_BADGE.free;

  /* User initials for avatar */
  const initials = session.user.name
    .split(" ")
    .map((n: string) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  return (
    <main className="mx-auto flex w-full max-w-lg flex-1 flex-col gap-6 px-4 py-12">
      {/* Avatar + heading */}
      <FadeIn>
        <div className="flex items-center gap-4 mb-2">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/15 ring-1 ring-primary/25 text-primary text-xl font-black flex-shrink-0">
            {initials}
          </div>
          <div>
            <h1
              className="text-2xl font-black text-foreground"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Account
            </h1>
            <p className="text-sm text-muted-foreground">Manage your profile and subscription.</p>
          </div>
        </div>
      </FadeIn>

      {/* Profile */}
      <FadeIn delay={0.1}>
        <section className="rounded-xl border border-border bg-card p-6 flex flex-col gap-4">
          <h2 className="text-sm font-bold text-muted-foreground uppercase tracking-widest">
            Profile
          </h2>
          <div className="grid gap-3 text-sm">
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Name</span>
              <span className="font-semibold text-foreground">{session.user.name}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Email</span>
              <span className="font-semibold text-foreground">{session.user.email}</span>
            </div>
          </div>
        </section>
      </FadeIn>

      {/* Plan */}
      <FadeIn delay={0.2}>
        <section className="rounded-xl border border-border bg-card p-6 flex flex-col gap-4">
          <h2 className="text-sm font-bold text-muted-foreground uppercase tracking-widest">
            Subscription
          </h2>
          <div className="grid gap-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Current plan</span>
              <span
                className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${badge.className}`}
              >
                {badge.label}
              </span>
            </div>
            {planExpiresAt && planTier !== "free" && (
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">Active until</span>
                <span className="font-semibold text-foreground">
                  {new Date(planExpiresAt).toLocaleDateString("en-IN", {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                </span>
              </div>
            )}
            {planTier === "free" && (
              <div className="mt-1 pt-1 border-t border-border/60">
                <p className="text-xs text-muted-foreground mb-3">
                  Unlock DXF export and BOQ Excel with Basic or Pro.
                </p>
                <Button
                  asChild
                  className="w-full bg-primary hover:bg-primary/90 text-primary-foreground font-bold btn-shine shadow-md shadow-primary/20"
                >
                  <Link href="/pricing">Upgrade Plan</Link>
                </Button>
              </div>
            )}
            {planTier !== "free" && (
              <p className="text-xs text-muted-foreground mt-1">
                To manage or cancel your subscription, contact us or visit the{" "}
                <a
                  href="https://dashboard.razorpay.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary underline underline-offset-4"
                >
                  Razorpay dashboard
                </a>
                .
              </p>
            )}
          </div>
        </section>
      </FadeIn>

      {/* Actions */}
      <FadeIn delay={0.3}>
        <div className="flex gap-3">
          <Button variant="outline" asChild>
            <Link href="/dashboard">← Dashboard</Link>
          </Button>
          {planTier === "free" && (
            <Button variant="outline" asChild>
              <Link href="/pricing">View pricing</Link>
            </Button>
          )}
        </div>
      </FadeIn>
    </main>
  );
}
