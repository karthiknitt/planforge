import { eq } from "drizzle-orm";
import { Crown, Users } from "lucide-react";
import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";
import { FadeIn } from "@/components/motion/fade-in";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { db } from "@/db";
import { teamMember as teamMemberTable, team as teamTable } from "@/db/schema";
import { auth } from "@/lib/auth";
import { CreateTeamForm } from "./create-team-form";
import { InviteMemberForm } from "./invite-member-form";
import { RemoveMemberButton } from "./remove-member-button";

export const metadata: Metadata = { title: "Team — PlanForge" };

export default async function TeamPage() {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/sign-in");

  const userId = session.user.id;

  // Find team membership
  const memberships = await db
    .select({ teamId: teamMemberTable.teamId, role: teamMemberTable.role })
    .from(teamMemberTable)
    .where(eq(teamMemberTable.userId, userId))
    .limit(1);

  if (memberships.length === 0) {
    return (
      <main className="mx-auto flex w-full max-w-lg flex-1 flex-col gap-6 px-4 py-12">
        <FadeIn>
          <div className="flex items-center gap-3 mb-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/25">
              <Users className="h-5 w-5 text-primary" />
            </div>
            <h1
              className="text-2xl font-black text-foreground"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Your Firm
            </h1>
          </div>
          <p className="text-sm text-muted-foreground mb-6">
            Create a team to share projects across your engineering firm. Requires a{" "}
            <Link href="/pricing" className="text-primary underline underline-offset-4">
              Firm plan
            </Link>
            .
          </p>
        </FadeIn>
        <FadeIn delay={0.1}>
          <section className="rounded-xl border border-border bg-card p-6">
            <h2 className="text-sm font-bold text-muted-foreground uppercase tracking-widest mb-4">
              Create Your Firm
            </h2>
            <CreateTeamForm userId={userId} />
          </section>
        </FadeIn>
        <FadeIn delay={0.2}>
          <Button variant="outline" asChild>
            <Link href="/dashboard">← Dashboard</Link>
          </Button>
        </FadeIn>
      </main>
    );
  }

  const { teamId, role } = memberships[0];
  const isAdmin = role === "admin";

  const [teamRows, members] = await Promise.all([
    db.select().from(teamTable).where(eq(teamTable.id, teamId)).limit(1),
    db.select().from(teamMemberTable).where(eq(teamMemberTable.teamId, teamId)),
  ]);

  const currentTeam = teamRows[0];

  return (
    <main className="mx-auto flex w-full max-w-lg flex-1 flex-col gap-6 px-4 py-12">
      <FadeIn>
        <div className="flex items-center gap-3 mb-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/25">
            <Users className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1
              className="text-2xl font-black text-foreground"
              style={{ fontFamily: "var(--font-display)" }}
            >
              {currentTeam.name}
            </h1>
            <p className="text-xs text-muted-foreground capitalize">
              {currentTeam.planTier} plan
              {currentTeam.planExpiresAt &&
                ` · expires ${new Date(currentTeam.planExpiresAt).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}`}
            </p>
          </div>
        </div>
      </FadeIn>

      {/* Members list */}
      <FadeIn delay={0.1}>
        <section className="rounded-xl border border-border bg-card p-6 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-muted-foreground uppercase tracking-widest">
              Members ({members.length} / 5)
            </h2>
          </div>

          <ul className="flex flex-col gap-2">
            {members.map((m) => (
              <li
                key={m.id}
                className="flex items-center justify-between gap-3 rounded-lg border border-border/50 bg-muted/30 px-4 py-3"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 flex-shrink-0">
                    {m.role === "admin" ? (
                      <Crown className="h-3.5 w-3.5 text-primary" />
                    ) : (
                      <Users className="h-3.5 w-3.5 text-muted-foreground" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {m.invitedEmail ?? (m.userId === userId ? "You" : m.userId)}
                    </p>
                    {m.userId === "" && (
                      <p className="text-[11px] text-muted-foreground">Invite pending</p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <Badge
                    variant="outline"
                    className={
                      m.role === "admin"
                        ? "border-primary/30 text-primary text-[10px]"
                        : "text-[10px]"
                    }
                  >
                    {m.role}
                  </Badge>
                  {isAdmin && m.userId !== userId && m.userId !== "" && (
                    <RemoveMemberButton teamId={teamId} targetUserId={m.userId} />
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      </FadeIn>

      {/* Invite form — admins only */}
      {isAdmin && members.length < 5 && (
        <FadeIn delay={0.2}>
          <section className="rounded-xl border border-border bg-card p-6 flex flex-col gap-4">
            <h2 className="text-sm font-bold text-muted-foreground uppercase tracking-widest">
              Invite Member
            </h2>
            <p className="text-xs text-muted-foreground">
              No email is sent automatically — share the invite link with your engineer manually.
            </p>
            <InviteMemberForm teamId={teamId} />
          </section>
        </FadeIn>
      )}

      {isAdmin && members.length >= 5 && (
        <FadeIn delay={0.2}>
          <p className="text-xs text-muted-foreground text-center rounded-lg border border-border/50 bg-muted/30 px-4 py-3">
            Maximum 5 members reached on the Firm plan.
          </p>
        </FadeIn>
      )}

      <FadeIn delay={0.3}>
        <Button variant="outline" asChild>
          <Link href="/dashboard">← Dashboard</Link>
        </Button>
      </FadeIn>
    </main>
  );
}
