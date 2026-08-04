"use client";

import { Check, LayoutGrid, Ruler, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useLocale } from "@/lib/locale-context";
import { cn } from "@/lib/utils";

const STEP_ICONS = [Ruler, LayoutGrid, Sparkles];

type OnboardingChecklistProps = {
  step1Done: boolean;
  step2Done: boolean;
  step3Done: boolean;
  firstProjectId: string | null;
};

export function OnboardingChecklist({
  step1Done,
  step2Done,
  step3Done,
  firstProjectId,
}: OnboardingChecklistProps) {
  const { t } = useLocale();
  const [dismissed, setDismissed] = useState(false);

  function dismiss() {
    setDismissed(true);
    fetch("/api/user/onboarding", { method: "PATCH" }).catch(() => {
      // Best-effort — worst case the checklist reappears next visit.
    });
  }

  if (dismissed) {
    return null;
  }

  const stepsDone = [step1Done, step2Done, step3Done];
  const completedCount = stepsDone.filter(Boolean).length;
  const firstIncomplete = stepsDone.findIndex((done) => !done);
  // All steps done can still render for one frame before the parent's
  // `showOnboarding` gate hides this — fall back to the last step so the
  // CTA/highlight logic below never indexes with -1.
  const currentStep = firstIncomplete === -1 ? 2 : firstIncomplete;

  const steps = [
    t("dashboard.onboardingStep1"),
    t("dashboard.onboardingStep2"),
    t("dashboard.onboardingStep3"),
  ];

  const ctaHref =
    currentStep === 0 || firstProjectId === null ? "/projects/new" : `/projects/${firstProjectId}`;
  const ctaLabel =
    currentStep === 0 ? t("dashboard.onboardingStartProject") : t("dashboard.onboardingContinue");

  return (
    <div className="animate-fade-up rounded-2xl border border-border/50 bg-card/40 backdrop-blur-sm p-5 sm:p-6 flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2
            className="text-lg font-black text-foreground"
            style={{ fontFamily: "var(--font-display)" }}
          >
            {t("dashboard.onboardingTitle")}
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {completedCount}/3 {t("dashboard.onboardingProgressLabel")}
          </p>
        </div>
        <button
          type="button"
          aria-label={t("dashboard.onboardingDismiss")}
          onClick={dismiss}
          className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted/60 hover:text-foreground transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <Progress value={(completedCount / 3) * 100} />

      <ol className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {steps.map((step, i) => {
          const Icon = STEP_ICONS[i];
          const done = stepsDone[i];
          const isCurrent = i === currentStep;
          return (
            <li
              key={step}
              className={cn(
                "flex items-start gap-3 rounded-xl p-2.5 ring-1 transition-colors",
                isCurrent ? "bg-primary/5 ring-primary/25" : "ring-transparent"
              )}
            >
              <span
                className={cn(
                  "flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg ring-1",
                  done
                    ? "bg-primary text-primary-foreground ring-primary"
                    : "bg-primary/10 text-primary ring-primary/20"
                )}
              >
                {done ? <Check className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
              </span>
              <span
                className={cn(
                  "text-sm pt-1.5",
                  done ? "text-muted-foreground line-through" : "text-foreground"
                )}
              >
                {step}
              </span>
            </li>
          );
        })}
      </ol>

      <div className="flex flex-col sm:flex-row gap-2">
        <Button variant="outline" asChild className="w-full sm:w-auto">
          <Link href="/gallery">{t("dashboard.onboardingBrowseTemplates")}</Link>
        </Button>
        <Button
          asChild
          className="w-full sm:w-auto bg-primary hover:bg-primary/90 text-primary-foreground font-bold btn-shine"
        >
          <Link href={ctaHref}>{ctaLabel}</Link>
        </Button>
      </div>
    </div>
  );
}
