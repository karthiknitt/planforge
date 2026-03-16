import { and, desc, eq, inArray, ne } from "drizzle-orm";
import { Building2, Users } from "lucide-react";
import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";
import { AnimatedFloorPlan } from "@/components/animated-floor-plan";
import { db } from "@/db";
import {
  project as projectTable,
  teamMember as teamMemberTable,
  user as userTable,
} from "@/db/schema";
import { auth } from "@/lib/auth";
import {
  DashboardEmptyState,
  DashboardMobileFAB,
  DashboardNewProjectButton,
  DashboardProjectCount,
  DashboardTitle,
  ProjectCardApprovalBadge,
  ProjectCardBuilding2Icon,
  ProjectCardViewLink,
} from "./dashboard-strings";

export const metadata: Metadata = { title: "Dashboard" };

const TIER_BADGE: Record<string, { label: string; className: string }> = {
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
  firm: {
    label: "Firm",
    className: "bg-purple-500/10 text-purple-400 border border-purple-500/20",
  },
};

export default async function DashboardPage() {
  const session = await auth.api.getSession({ headers: await headers() });

  if (!session) {
    redirect("/sign-in");
  }

  const [myProjects, userRows, teamMemberships] = await Promise.all([
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
    db
      .select({ teamId: teamMemberTable.teamId })
      .from(teamMemberTable)
      .where(eq(teamMemberTable.userId, session.user.id)),
  ]);

  const teamIds = teamMemberships.map((m) => m.teamId);
  const teamProjects =
    teamIds.length > 0
      ? await db
          .select()
          .from(projectTable)
          .where(
            and(inArray(projectTable.teamId, teamIds), ne(projectTable.userId, session.user.id))
          )
          .orderBy(desc(projectTable.createdAt))
      : [];

  const projects = myProjects;
  const planTier = userRows[0]?.planTier ?? "free";
  const badge = TIER_BADGE[planTier] ?? TIER_BADGE.free;

  const firstName = session.user.name.split(" ")[0];

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 sm:gap-10 px-4 sm:px-6 py-8 sm:py-14">
      {/* Header */}
      <div className="animate-fade-up">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <DashboardTitle firstName={firstName} />
              <span
                className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${badge.className}`}
              >
                {badge.label}
              </span>
            </div>
            <DashboardProjectCount count={projects.length} planTier={planTier} />
          </div>
          <DashboardNewProjectButton />
        </div>
      </div>

      {/* Projects */}
      {projects.length === 0 ? (
        <div className="animate-fade-up delay-200 rounded-2xl border border-dashed border-border/50 p-16 text-center flex flex-col items-center bg-card/20">
          <div className="mx-auto mb-8 w-[160px] opacity-40 pointer-events-none">
            <AnimatedFloorPlan />
          </div>
          <DashboardEmptyState />
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
                  <ProjectCardBuilding2Icon name={p.name} />
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

                {/* Approval badge */}
                {p.approvalStatus && (
                  <div className="flex items-center gap-1.5">
                    <ProjectCardApprovalBadge status={p.approvalStatus} />
                  </div>
                )}

                {/* Footer */}
                <div className="mt-auto pt-2 flex items-center justify-between border-t border-border/30">
                  <span className="text-[11px] text-muted-foreground/70">
                    {new Date(p.createdAt).toLocaleDateString("en-IN", {
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })}
                  </span>
                  <ProjectCardViewLink />
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}

      {/* Team Projects section */}
      {teamProjects.length > 0 && (
        <div className="animate-fade-up delay-300 flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-muted-foreground" />
            <h2
              className="text-base font-bold text-foreground"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Team Projects
            </h2>
            <span className="text-xs text-muted-foreground">({teamProjects.length})</span>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {teamProjects.map((p, i) => (
              <Link
                key={p.id}
                href={`/projects/${p.id}`}
                className="animate-fade-up block h-full group"
                style={{ animationDelay: `${100 + i * 60}ms` }}
              >
                <div className="feature-card rounded-2xl border border-border/50 bg-card/40 backdrop-blur-sm p-5 flex flex-col gap-3 h-full">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/8 ring-1 ring-primary/15">
                        <Building2 className="h-4 w-4 text-primary/70" />
                      </div>
                      <span className="font-bold text-sm text-foreground group-hover:text-primary transition-colors line-clamp-1">
                        {p.name}
                      </span>
                    </div>
                    <span className="inline-flex items-center gap-1 rounded-full border border-purple-500/30 bg-purple-500/10 px-2 py-0.5 text-[10px] font-medium text-purple-400 flex-shrink-0">
                      <Users className="h-2.5 w-2.5" />
                      Shared
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <span className="inline-flex items-center rounded-md bg-muted/50 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                      {p.plotLength} &times; {p.plotWidth} m
                    </span>
                    <span className="inline-flex items-center rounded-md bg-muted/50 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                      {p.numBedrooms} BHK &middot; {p.toilets}T{p.parking ? " \u00B7 P" : ""}
                    </span>
                  </div>
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
        </div>
      )}
      {/* Mobile FAB — fixed bottom-right, replaces top-right button on small screens */}
      <DashboardMobileFAB />
    </main>
  );
}
