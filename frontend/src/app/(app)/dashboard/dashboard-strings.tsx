"use client";

import { Building2, Plus, Users } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import type { project } from "@/db/schema";
import { useLocale } from "@/lib/locale-context";
import { showToast } from "@/lib/toast";

type Project = typeof project.$inferSelect;

// Confirms a Razorpay checkout that redirected back here — the checkout
// buttons themselves unmount on navigation, so success can only be
// acknowledged after landing on this page. Strips the query param so a
// refresh doesn't re-toast.
export function DashboardPaymentToast() {
  const searchParams = useSearchParams();
  const router = useRouter();

  useEffect(() => {
    if (searchParams.get("credits_added")) {
      showToast("success", "Credits added to your account");
      router.replace("/dashboard");
    } else if (searchParams.get("upgraded")) {
      showToast("success", "Plan upgraded");
      router.replace("/dashboard");
    }
  }, [searchParams, router]);

  return null;
}

export function DashboardNewProjectButton() {
  const { t } = useLocale();
  return (
    <Button
      asChild
      className="hidden sm:flex bg-primary hover:bg-primary/90 text-primary-foreground font-bold btn-shine shadow-md shadow-primary/15 flex-shrink-0 h-10"
    >
      <Link href="/projects/new">
        <Plus className="h-4 w-4 mr-1.5" />
        {t("dashboard.newProject")}
      </Link>
    </Button>
  );
}

export function DashboardMobileFAB() {
  return (
    <Link
      href="/projects/new"
      aria-label="New Project"
      className="sm:hidden fixed bottom-6 right-5 z-30 flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-xl shadow-primary/30 hover:bg-primary/90 active:scale-95 transition-all"
    >
      <Plus className="h-6 w-6" />
    </Link>
  );
}

export function DashboardEmptyState() {
  const { t } = useLocale();
  return (
    <>
      <h3
        className="text-lg font-bold text-foreground mb-2"
        style={{ fontFamily: "var(--font-display)" }}
      >
        {t("dashboard.noProjects")}
      </h3>
      <p className="text-sm text-muted-foreground mb-8 max-w-xs">{t("dashboard.noProjectsHint")}</p>
      <Button
        asChild
        className="bg-primary hover:bg-primary/90 text-primary-foreground btn-shine shadow-md shadow-primary/15"
      >
        <Link href="/projects/new">
          <Plus className="h-4 w-4 mr-1.5" />
          {t("dashboard.createFirstProject")}
        </Link>
      </Button>
    </>
  );
}

export function DashboardTitle({ firstName }: { firstName: string }) {
  const { t } = useLocale();
  return (
    <h1
      className="text-2xl sm:text-3xl font-black text-foreground"
      style={{ fontFamily: "var(--font-display)" }}
    >
      {t("dashboard.welcomeBack")}, <span className="text-gradient-orange">{firstName}</span>
    </h1>
  );
}

export function DashboardUpgradeHint() {
  const { t } = useLocale();
  return (
    <>
      {" · "}
      <Link href="/pricing" className="text-primary hover:underline underline-offset-4 font-medium">
        {t("dashboard.upgradeForFeatures")}
      </Link>{" "}
      {t("dashboard.upgradeHint")}
    </>
  );
}

export function ProjectCardApprovalBadge({ status }: { status: string }) {
  const { t } = useLocale();
  if (status === "approved") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-green-500/30 bg-green-500/10 px-2 py-0.5 text-[11px] font-medium text-green-700 dark:text-green-400">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-green-500" />
        {t("dashboard.approved")}
      </span>
    );
  }
  if (status === "changes_requested") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-orange-500/30 bg-orange-500/10 px-2 py-0.5 text-[11px] font-medium text-orange-700 dark:text-orange-400">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-orange-500" />
        {t("dashboard.changesRequested")}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/50 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-muted-foreground/50" />
      {t("dashboard.awaiting")}
    </span>
  );
}

export function ProjectCardViewLink() {
  const { t } = useLocale();
  return (
    <span className="text-xs font-medium text-primary/70 group-hover:text-primary transition-colors">
      {t("dashboard.viewProject")} &rarr;
    </span>
  );
}

export function DashboardProjectCount({ count, planTier }: { count: number; planTier: string }) {
  return (
    <p className="text-sm text-muted-foreground">
      {count} project{count !== 1 ? "s" : ""}
      {planTier === "free" && <DashboardUpgradeHint />}
    </p>
  );
}

export function ProjectCardBuilding2Icon({ name }: { name: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/8 ring-1 ring-primary/15">
        <Building2 className="h-4 w-4 text-primary/70" />
      </div>
      <span className="font-bold text-sm text-foreground group-hover:text-primary transition-colors line-clamp-1">
        {name}
      </span>
    </div>
  );
}

export function ProjectCard({
  project,
  variant,
  animationDelayMs,
}: {
  project: Project;
  variant: "own" | "team";
  animationDelayMs: number;
}) {
  return (
    <Link
      href={`/projects/${project.id}`}
      className="animate-fade-up block h-full group"
      style={{ animationDelay: `${animationDelayMs}ms` }}
    >
      <div className="feature-card rounded-2xl border border-border/50 bg-card/40 backdrop-blur-sm p-5 flex flex-col gap-3 h-full">
        <div className="flex items-start justify-between gap-2">
          <ProjectCardBuilding2Icon name={project.name} />
          {variant === "team" && (
            <span className="inline-flex items-center gap-1 rounded-full border border-purple-500/30 bg-purple-500/10 px-2 py-0.5 text-[10px] font-medium text-purple-400 flex-shrink-0">
              <Users className="h-2.5 w-2.5" />
              Shared
            </span>
          )}
        </div>

        <div className="flex flex-wrap gap-1.5">
          <span className="inline-flex items-center rounded-md bg-muted/50 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
            {project.plotLength} &times; {project.plotWidth} m
          </span>
          <span className="inline-flex items-center rounded-md bg-muted/50 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
            {project.numBedrooms} BHK &middot; {project.toilets}T{project.parking ? " · P" : ""}
          </span>
          {variant === "own" && project.city && project.city !== "other" && (
            <span className="inline-flex items-center rounded-full bg-primary/8 text-primary/70 px-2 py-0.5 text-[11px] font-medium capitalize">
              {project.city}
            </span>
          )}
        </div>

        {variant === "own" && project.approvalStatus && (
          <div className="flex items-center gap-1.5">
            <ProjectCardApprovalBadge status={project.approvalStatus} />
          </div>
        )}

        <div className="mt-auto pt-2 flex items-center justify-between border-t border-border/30">
          <span className="text-[11px] text-muted-foreground">
            {new Date(project.createdAt).toLocaleDateString("en-IN", {
              day: "numeric",
              month: "short",
              year: "numeric",
            })}
          </span>
          <ProjectCardViewLink />
        </div>
      </div>
    </Link>
  );
}
