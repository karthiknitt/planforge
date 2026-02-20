import { eq } from "drizzle-orm";
import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";
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

  const TIER_BADGE = {
    free: {
      label: "Free",
      className: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
    },
    basic: {
      label: "Basic",
      className: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
    },
    pro: {
      label: "Pro",
      className: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
    },
  };
  const badge = TIER_BADGE[planTier as keyof typeof TIER_BADGE] ?? TIER_BADGE.free;

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-12">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1
              className="text-2xl font-bold"
              style={{ fontFamily: "var(--font-display)" }}
            >{`Welcome, ${session.user.name}`}</h1>
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${badge.className}`}>
              {badge.label}
            </span>
          </div>
          <p className="mt-1 text-muted-foreground">
            Your floor plan projects
            {planTier === "free" && (
              <>
                {" "}
                &middot;{" "}
                <Link href="/pricing" className="text-foreground underline underline-offset-4">
                  Upgrade
                </Link>{" "}
                for DXF + BOQ Excel
              </>
            )}
          </p>
        </div>
        <Button asChild className="bg-[#f97316] hover:bg-[#ea6c0a] text-white font-semibold">
          <Link href="/projects/new">+ New project</Link>
        </Button>
      </div>

      {projects.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground">
          No projects yet.{" "}
          <Link href="/projects/new" className="text-foreground underline underline-offset-4">
            Create your first project
          </Link>{" "}
          to get started.
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <div
              key={p.id}
              className="feature-card rounded-2xl border border-border bg-card p-5 flex flex-col gap-3 hover:border-primary/30"
            >
              <div className="font-bold text-base">{p.name}</div>
              <div className="flex flex-wrap gap-1.5">
                <span className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                  {p.plot_length} &times; {p.plot_width} m
                </span>
                <span className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                  {p.num_bedrooms} BHK &middot; {p.toilets}T{p.parking ? " \u00B7 Parking" : ""}
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
          ))}
        </div>
      )}
    </main>
  );
}
