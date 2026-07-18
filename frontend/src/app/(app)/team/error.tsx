"use client";

import { RouteError } from "@/components/route-error";

export default function TeamError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <RouteError error={error} reset={reset} message="Could not load your team. Please try again." />
  );
}
