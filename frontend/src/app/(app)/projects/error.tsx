"use client";

import { RouteError } from "@/components/route-error";

export default function ProjectsListError({
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
      message="Could not load your projects. Please try again."
    />
  );
}
