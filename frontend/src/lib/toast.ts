// Thin sonner wrapper reusing the StatusTone vocabulary from
// structural-status.ts so new toasts stay visually consistent with the
// Stage 2 lifecycle badges instead of introducing new colors.
import { toast } from "sonner";
import type { StatusTone } from "@/lib/structural-status";

type TonedToast = Exclude<StatusTone, "muted">;

// Looked up by name at call time (not pre-bound) so tests can mock
// toast.success/warning/info individually.
const TONE_TO_METHOD: Record<TonedToast, "success" | "warning" | "info"> = {
  success: "success",
  warning: "warning",
  info: "info",
};

export function showToast(tone: TonedToast, message: string): void {
  toast[TONE_TO_METHOD[tone]](message);
}

export function showErrorToast(message: string): void {
  toast.error(message);
}
