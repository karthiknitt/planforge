"use client";

import { RouteError } from "@/components/route-error";

export default function NewProjectError({
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
      message="Could not load the new project form. Please try again."
    />
  );
}
