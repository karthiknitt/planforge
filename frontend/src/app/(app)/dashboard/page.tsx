import { desc, eq } from "drizzle-orm";
import { Building2, Plus } from "lucide-react";
import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";
import { AnimatedFloorPlan } from "@/components/animated-floor-plan";
import { Button } from "@/components/ui/button";
import { db } from "@/db";
import { project as projectTable, user as userTable } from "@/db/schema";
import { auth } from "@/lib/auth";

export const metadata: Metadata = { title: "Dashboard" };

const TIER_BADGE = {
  free: {
    label: "Free",
    className: "bg-muted/80 text-muted-foreground border border-border/60",
  },
  basic: {
    label: "Basic",
    className: "bg-blue-500/10 text-blue-400 border border-blue-500/20",
  },
  pro: {
    label: "Pro",
    className: "bg-primary/10 text-primary border border-primary/25",
  },
};

export default async function DashboardPage() {
  const session = await auth.api.getSession({ headers: await headers() });

  if (!session) {
    redirect("/sign-in");
  }

  const [projects, userRows] = await Promise.all([
    db
      .select()
      .from(projectTable)
      .where(eq(projectTable.userId, session.user.id))
      .orderBy(desc(projectTable.createdAt)),
    db
      .select({ planTier: userTable.planTier })
      .from(userTable)
      .where(eq(userTable.id, session.user.id))
      .limit(1),
  ]);
  const planTier = userRows[0]?.planTier ?? "free";
  const badge = TIER_BADGE[planTier as keyof typeof TIER_BADGE] ?? TIER_BADGE.free;

  const firstName = session.user.name.split(" ")[0];

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-10 px-4 sm:px-6 py-10 sm:py-14">
      {/* Header */}
      <div className="animate-fade-up">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1
                className="text-2xl sm:text-3xl font-black text-foreground"
                style={{ fontFamily: "var(--font-display)" }}
              >
                Welcome back, <span className="text-gradient-orange">{firstName}</span>
              </h1>
              <span
                className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${badge.className}`}
              >
                {badge.label}
              </span>
            </div>
            <p className="text-sm text-muted-foreground">
              {projects.length} project{projects.length !== 1 ? "s" : ""}
              {planTier === "free" && (
                <>
                  {" \u00B7 "}
                  <Link
                    href="/pricing"
                    className="text-primary hover:underline underline-offset-4 font-medium"
                  >
                    Upgrade
                  </Link>{" "}
                  for DXF + BOQ
                </>
              )}
            </p>
          </div>
          <Button
            asChild
            className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold btn-shine shadow-md shadow-primary/15 flex-shrink-0 h-10"
          >
            <Link href="/projects/new">
              <Plus className="h-4 w-4 mr-1.5" />
              New project
            </Link>
          </Button>
        </div>
      </div>

      {/* Projects */}
      {projects.length === 0 ? (
        <div className="animate-fade-up delay-200 rounded-2xl border border-dashed border-border/50 p-16 text-center flex flex-col items-center bg-card/20">
          <div className="mx-auto mb-8 w-[160px] opacity-40 pointer-events-none">
            <AnimatedFloorPlan />
          </div>
          <h3
            className="text-lg font-bold text-foreground mb-2"
            style={{ fontFamily: "var(--font-display)" }}
          >
            No projects yet
          </h3>
          <p className="text-sm text-muted-foreground mb-8 max-w-xs">
            Create your first floor plan project and get 5 NBC-compliant layout variations in
            seconds.
          </p>
          <Button
            asChild
            className="bg-primary hover:bg-primary/90 text-primary-foreground btn-shine shadow-md shadow-primary/15"
          >
            <Link href="/projects/new">
              <Plus className="h-4 w-4 mr-1.5" />
              Create first project
            </Link>
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p, i) => (
            <Link
              key={p.id}
              href={`/projects/${p.id}`}
              className="animate-fade-up block h-full group"
              style={{ animationDelay: `${100 + i * 60}ms` }}
            >
              <div className="feature-card rounded-2xl border border-border/50 bg-card/40 backdrop-blur-sm p-5 flex flex-col gap-3 h-full">
                {/* Project header */}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/8 ring-1 ring-primary/15">
                      <Building2 className="h-4 w-4 text-primary/70" />
                    </div>
                    <span className="font-bold text-sm text-foreground group-hover:text-primary transition-colors line-clamp-1">
                      {p.name}
                    </span>
                  </div>
                </div>

                {/* Tags */}
                <div className="flex flex-wrap gap-1.5">
                  <span className="inline-flex items-center rounded-md bg-muted/50 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                    {p.plotLength} &times; {p.plotWidth} m
                  </span>
                  <span className="inline-flex items-center rounded-md bg-muted/50 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                    {p.numBedrooms} BHK &middot; {p.toilets}T{p.parking ? " \u00B7 P" : ""}
                  </span>
                  {p.city && p.city !== "other" && (
                    <span className="inline-flex items-center rounded-full bg-primary/8 text-primary/70 px-2 py-0.5 text-[11px] font-medium capitalize">
                      {p.city}
                    </span>
                  )}
                </div>

                {/* Footer */}
                <div className="mt-auto pt-2 flex items-center justify-between border-t border-border/30">
                  <span className="text-[11px] text-muted-foreground/70">
                    {new Date(p.createdAt).toLocaleDateString("en-IN", {
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })}
                  </span>
                  <span className="text-xs font-medium text-primary/70 group-hover:text-primary transition-colors">
                    View &rarr;
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
