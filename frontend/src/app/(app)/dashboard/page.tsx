import { Plus } from "lucide-react";
import { eq } from "drizzle-orm";
import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";
import { AnimatedFloorPlan } from "@/components/animated-floor-plan";
import { FadeIn } from "@/components/motion/fade-in";
import { StaggerChildren, StaggerItem } from "@/components/motion/stagger-children";
import { Button } from "@/components/ui/button";
import { db } from "@/db";
import { user as userTable } from "@/db/schema";
import { auth } from "@/lib/auth";

export const metadata: Metadata = { title: "Dashboard" };

interface Project {
  id: string;
  name: string;
  plot_length: number;
  plot_width: number;
  num_bedrooms: number;
  toilets: number;
  parking: boolean;
  city: string | null;
  created_at: string;
}

async function fetchProjects(userId: string): Promise<Project[]> {
  try {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/projects`, {
      headers: { "X-User-Id": userId },
      cache: "no-store",
    });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

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

export default async function DashboardPage() {
  const session = await auth.api.getSession({ headers: await headers() });

  if (!session) {
    redirect("/sign-in");
  }

  const projects = await fetchProjects(session.user.id);

  const userRows = await db
    .select({ planTier: userTable.planTier })
    .from(userTable)
    .where(eq(userTable.id, session.user.id))
    .limit(1);
  const planTier = userRows[0]?.planTier ?? "free";
  const badge = TIER_BADGE[planTier as keyof typeof TIER_BADGE] ?? TIER_BADGE.free;

  const firstName = session.user.name.split(" ")[0];

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-4 py-12">
      {/* Header */}
      <FadeIn>
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5 mb-1">
              <h1
                className="text-2xl font-black text-foreground"
                style={{ fontFamily: "var(--font-display)" }}
              >
                Welcome,{" "}
                <span className="text-gradient-orange">{firstName}</span>
              </h1>
              <span
                className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${badge.className}`}
              >
                {badge.label}
              </span>
            </div>
            <p className="text-sm text-muted-foreground">
              Your floor plan projects
              {planTier === "free" && (
                <>
                  {" "}
                  &middot;{" "}
                  <Link href="/pricing" className="text-primary hover:underline underline-offset-4 font-medium">
                    Upgrade
                  </Link>{" "}
                  for DXF + BOQ Excel
                </>
              )}
            </p>
          </div>
          <Button
            asChild
            className="bg-primary hover:bg-primary/90 text-primary-foreground font-semibold btn-shine shadow-md shadow-primary/20 flex-shrink-0"
          >
            <Link href="/projects/new">
              <Plus className="h-4 w-4 mr-1.5" />
              New project
            </Link>
          </Button>
        </div>
      </FadeIn>

      {/* Projects */}
      {projects.length === 0 ? (
        <FadeIn delay={0.15}>
          <div className="rounded-2xl border border-dashed border-border p-12 text-center flex flex-col items-center">
            <div className="mx-auto mb-6 w-[180px] opacity-50 pointer-events-none">
              <AnimatedFloorPlan />
            </div>
            <h3
              className="text-lg font-bold text-foreground mb-2"
              style={{ fontFamily: "var(--font-display)" }}
            >
              No projects yet
            </h3>
            <p className="text-sm text-muted-foreground mb-6 max-w-xs">
              Create your first floor plan project and get 5 NBC-compliant layout variations in
              seconds.
            </p>
            <Button
              asChild
              className="bg-primary hover:bg-primary/90 text-primary-foreground btn-shine shadow-md shadow-primary/20"
            >
              <Link href="/projects/new">
                <Plus className="h-4 w-4 mr-1.5" />
                Create first project
              </Link>
            </Button>
          </div>
        </FadeIn>
      ) : (
        <StaggerChildren className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <StaggerItem key={p.id}>
              <div className="feature-card rounded-2xl border border-border bg-card p-5 flex flex-col gap-3 hover:border-primary/30 transition-transform duration-200 hover:-translate-y-1 h-full">
                <div className="font-bold text-base text-foreground">{p.name}</div>
                <div className="flex flex-wrap gap-1.5">
                  <span className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                    {p.plot_length} &times; {p.plot_width} m
                  </span>
                  <span className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                    {p.num_bedrooms} BHK &middot; {p.toilets}T
                    {p.parking ? " \u00B7 Parking" : ""}
                  </span>
                  {p.city && p.city !== "other" && (
                    <span className="inline-flex items-center rounded-full bg-primary/10 text-primary px-2.5 py-0.5 text-xs font-medium capitalize">
                      {p.city}
                    </span>
                  )}
                </div>
                <div className="text-xs text-muted-foreground">
                  {new Date(p.created_at).toLocaleDateString("en-IN", {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                </div>
                <div className="mt-auto flex gap-2 pt-1">
                  <Button
                    size="sm"
                    className="bg-primary text-primary-foreground hover:bg-primary/90"
                    asChild
                  >
                    <Link href={`/projects/${p.id}`}>View &rarr;</Link>
                  </Button>
                  <Button variant="ghost" size="sm" asChild>
                    <Link href={`/projects/${p.id}/edit`}>Edit</Link>
                  </Button>
                </div>
              </div>
            </StaggerItem>
          ))}
        </StaggerChildren>
      )}
    </main>
  );
}
