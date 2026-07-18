"use client";

import { LayoutGrid, Ruler, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useLocale } from "@/lib/locale-context";

const STEP_ICONS = [Ruler, LayoutGrid, Sparkles];

export function OnboardingModal() {
  const { t } = useLocale();
  const [open, setOpen] = useState(true);

  function dismiss() {
    setOpen(false);
    fetch("/api/user/onboarding", { method: "PATCH" }).catch(() => {
      // Best-effort — worst case the modal reappears next visit.
    });
  }

  const steps = [
    t("dashboard.onboardingStep1"),
    t("dashboard.onboardingStep2"),
    t("dashboard.onboardingStep3"),
  ];

  return (
    <Dialog open={open} onOpenChange={(next) => !next && dismiss()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle
            className="text-xl font-black text-foreground"
            style={{ fontFamily: "var(--font-display)" }}
          >
            {t("dashboard.onboardingTitle")}
          </DialogTitle>
        </DialogHeader>

        <ol className="flex flex-col gap-3 py-2">
          {steps.map((step, i) => {
            const Icon = STEP_ICONS[i];
            return (
              <li key={step} className="flex items-start gap-3">
                <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 ring-1 ring-primary/20">
                  <Icon className="h-4 w-4 text-primary" />
                </span>
                <span className="text-sm text-muted-foreground pt-1.5">{step}</span>
              </li>
            );
          })}
        </ol>

        <DialogFooter className="flex-col sm:flex-row gap-2">
          <Button variant="outline" asChild onClick={dismiss} className="w-full sm:w-auto">
            <Link href="/gallery">{t("dashboard.onboardingBrowseTemplates")}</Link>
          </Button>
          <Button
            asChild
            onClick={dismiss}
            className="w-full sm:w-auto bg-primary hover:bg-primary/90 text-primary-foreground font-bold btn-shine"
          >
            <Link href="/projects/new">{t("dashboard.onboardingStartProject")}</Link>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
