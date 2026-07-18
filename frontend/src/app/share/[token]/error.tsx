"use client";

import { RouteError } from "@/components/route-error";

export default function ShareError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <RouteError
      error={error}
      reset={reset}
      message="Could not load this shared plan. Please try again."
      fullScreen
    />
  );
}
