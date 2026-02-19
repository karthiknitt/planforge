import { eq } from "drizzle-orm";
import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Button } from "@/components/ui/button";
import { db } from "@/db";
import { user as userTable } from "@/db/schema";
import { auth } from "@/lib/auth";

export const metadata: Metadata = { title: "Account — PlanForge" };

const TIER_BADGE = {
  free: { label: "Free", className: "bg-slate-100 text-slate-600" },
  basic: { label: "Basic", className: "bg-blue-100 text-blue-700" },
  pro: { label: "Pro", className: "bg-amber-100 text-amber-700" },
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

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-8 px-4 py-10">
      <div>
        <h1 className="text-2xl font-bold">Account</h1>
        <p className="mt-1 text-muted-foreground">Manage your profile and subscription.</p>
      </div>

      {/* Profile */}
      <section className="rounded-xl border bg-card p-6 flex flex-col gap-4">
        <h2 className="text-base font-semibold">Profile</h2>
        <div className="grid gap-3 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Name</span>
            <span className="font-medium">{session.user.name}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Email</span>
            <span className="font-medium">{session.user.email}</span>
          </div>
        </div>
      </section>

      {/* Plan */}
      <section className="rounded-xl border bg-card p-6 flex flex-col gap-4">
        <h2 className="text-base font-semibold">Subscription</h2>
        <div className="grid gap-3 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Current plan</span>
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${badge.className}`}>
              {badge.label}
            </span>
          </div>
          {planExpiresAt && planTier !== "free" && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">Active until</span>
              <span className="font-medium">
                {new Date(planExpiresAt).toLocaleDateString("en-IN", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </span>
            </div>
          )}
          {planTier === "free" && (
            <div className="mt-2">
              <Button asChild className="bg-[#f97316] hover:bg-[#ea6c0a] text-white font-bold">
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
                className="underline underline-offset-4"
              >
                Razorpay dashboard
              </a>
              .
            </p>
          )}
        </div>
      </section>

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
    </main>
  );
}
