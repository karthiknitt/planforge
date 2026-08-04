import { and, desc, eq, inArray, ne } from "drizzle-orm";
import { Users } from "lucide-react";
import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { AnimatedFloorPlan } from "@/components/animated-floor-plan";
import { db } from "@/db";
import {
  project as projectTable,
  teamMember as teamMemberTable,
  user as userTable,
} from "@/db/schema";
import { auth } from "@/lib/auth";
import { TIER_BADGE } from "@/lib/tier-badge";
import {
  DashboardEmptyState,
  DashboardMobileFAB,
  DashboardNewProjectButton,
  DashboardPaymentToast,
  DashboardProjectCount,
  DashboardTitle,
  ProjectCard,
} from "./dashboard-strings";
import { OnboardingModal } from "./onboarding-modal";

export const metadata: Metadata = { title: "Dashboard" };

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
      .select({ planTier: userTable.planTier, hasSeenOnboarding: userTable.hasSeenOnboarding })
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
  const showOnboarding = projects.length === 0 && !userRows[0]?.hasSeenOnboarding;

  const firstName = session.user.name.split(" ")[0];

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 sm:gap-10 px-4 sm:px-6 py-8 sm:py-14">
      <Suspense fallback={null}>
        <DashboardPaymentToast />
      </Suspense>
      {showOnboarding && <OnboardingModal />}
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
            <ProjectCard key={p.id} project={p} variant="own" animationDelayMs={100 + i * 60} />
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
              <ProjectCard key={p.id} project={p} variant="team" animationDelayMs={100 + i * 60} />
            ))}
          </div>
        </div>
      )}
      {/* Mobile FAB — fixed bottom-right, replaces top-right button on small screens */}
      <DashboardMobileFAB />
    </div>
  );
}
